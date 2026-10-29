from contextlib import asynccontextmanager
import json
import logging
from math import isfinite
from typing import Literal
import asyncpg
from fastapi import FastAPI,Header,HTTPException,Query
from .models import *
from .service import ExecutionService,decode_json
from .settings import settings
from pydantic import BaseModel,Field,model_validator
from uuid import UUID,uuid4
from time import time

def analyze_trades(items: list[dict]):
    total=len(items);wins=[item for item in items if item.get("pnl",0)>0];losses=[item for item in items if item.get("pnl",0)<0]
    gross_profit=sum(float(item.get("pnl",0)) for item in wins);gross_loss=abs(sum(float(item.get("pnl",0)) for item in losses))
    r_values=[float(item["r_multiple"]) for item in items if item.get("r_multiple") is not None]
    entry_points=[]
    for item in items:
        pnl=float(item.get("pnl",0));mfe=max(float(item.get("max_unrealized_pnl",0)),0)
        entry_points.append({
            "position_id":item.get("position_id"),"symbol":item.get("symbol"),"direction":item.get("direction"),
            "entry_price":item.get("entry_price"),"exit_price":item.get("exit_price"),"initial_stop_loss_price":item.get("initial_stop_loss_price"),
            "pnl":pnl,"pnl_percent":float(item.get("pnl_percent",0)),"r_multiple":item.get("r_multiple"),
            "capture_rate":pnl/mfe*100 if pnl>0 and mfe>0 else None,"duration_seconds":int(item.get("duration_seconds",0)),
            "reason":item.get("reason"),"closed_at":item.get("closed_at"),
        })
    return {"metrics":{"total_trades":total,"net_pnl":sum(float(x.get("pnl",0)) for x in items),
        "win_rate":len(wins)/total*100 if total else 0,"profit_factor":gross_profit/gross_loss if gross_loss else None,
        "expectancy":sum(float(x.get("pnl",0)) for x in items)/total if total else 0,
        "payoff_ratio":(gross_profit/len(wins))/(gross_loss/len(losses)) if wins and losses else None,
        "average_r":sum(r_values)/len(r_values) if r_values else None,
        "average_duration_seconds":sum(int(x.get("duration_seconds",0)) for x in items)/total if total else 0},
        "entry_points":entry_points}

class TradingConfigCreate(BaseModel):
    symbol: str
    mode: str = "SIMULATION"
    config: dict
    @property
    def normalized_mode(self):return self.mode.strip().upper()
    @model_validator(mode="after")
    def validate_live_risk(self):
        def value(camel,snake,default):return self.config.get(camel,self.config.get(snake,default))
        try:
            initial=float(value("initialCapital","initial_capital",0))
            current=float(value("currentCapital","current_capital",initial))
            risk=float(value("riskPerTradePercent","risk_per_trade_percent",1))
            leverage=int(value("leverage","leverage",1))
            allocation=float(value("portfolioAllocationPercent","portfolio_allocation_percent",100))
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError("invalid numeric trading configuration") from exc
        if str(value("strategy","strategy","")).upper()!="ELLIOTT":raise ValueError("only ELLIOTT strategy is supported")
        if not isfinite(initial) or not isfinite(current) or initial<=0 or current<=0:raise ValueError("initial and current capital must be finite and positive")
        if not isfinite(risk) or risk<0:raise ValueError("risk per trade must be finite and not negative")
        if not 1<=leverage<=125:raise ValueError("leverage must be between 1 and 125")
        if not isfinite(allocation) or not 0<allocation<=100:raise ValueError("portfolio allocation must be finite and between 0 and 100")
        if value("portfolioCapitalMode","portfolio_capital_mode","SEQUENTIAL") not in {"ALLOCATED","SEQUENTIAL"}:
            raise ValueError("unsupported portfolio capital mode")
        return self

class StrategyConfigurationWrite(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    description:str=Field(default="",max_length=1000)
    config:dict

class PortfolioAssetWrite(BaseModel):
    symbol:str=Field(min_length=1,max_length=80)
    configuration_id:UUID
    allocation_percent:float=Field(gt=0,le=100)

class PortfolioWrite(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    description:str=Field(default="",max_length=1000)
    assets:list[PortfolioAssetWrite]=Field(min_length=1,max_length=100)

class PortfolioLiveRequest(BaseModel):
    mode:str="PAPER"
    capital:float=Field(gt=0)
    capital_mode:Literal["ALLOCATED","SEQUENTIAL"]="SEQUENTIAL"

def configuration_record(row):
    value=dict(row);value["id"]=str(value["id"])
    value["config"]=decode_json(value["config"])
    value["created_at"]=value["created_at"].isoformat();value["updated_at"]=value["updated_at"].isoformat()
    return value

def portfolio_record(row):
    value=dict(row);value["id"]=str(value["id"]);value["assets"]=decode_json(value["assets"])
    value["created_at"]=value["created_at"].isoformat();value["updated_at"]=value["updated_at"].isoformat()
    return value

service=ExecutionService(settings.database_url,settings.redis_url,settings.stream_group,settings.consumer_name,
  settings.execution_mode,settings.exchange_service_url,settings.backtest_service_url)
@asynccontextmanager
async def lifespan(app):await service.start();yield;await service.stop()
app=FastAPI(title="Execution and Position Service",version="1.0.0",lifespan=lifespan)
log=logging.getLogger(__name__)

@app.get("/health")
async def health():
    try:
        await service.redis.ping();await service.db.fetchval("SELECT 1")
        if not service.tasks or any(task.done() for task in service.tasks):raise RuntimeError("Trading worker has stopped")
        return {"status":"UP","mode":service.mode}
    except Exception as exc:raise HTTPException(503,"Dependency unavailable") from exc
@app.get("/orders")
async def orders(symbol:str|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
    items=sorted(service.orders.values(),key=lambda x:x.created_at,reverse=True)
    if symbol:items=[x for x in items if x.symbol==symbol.upper()]
    if status:items=[x for x in items if x.status==status.upper()]
    return {"orders":items[offset:offset+limit],"total":len(items)}
@app.post("/orders",status_code=201)
async def create_order(data:OrderCreate):
    raise HTTPException(403,"Manual orders are disabled: only Elliott signals can be executed")
@app.get("/orders/{order_id}")
async def order(order_id:str):
    item=service.orders.get(order_id)
    if not item:raise HTTPException(404,"Order not found")
    return item
async def cancel_order(order_id:str):
    item=service.orders.get(order_id)
    if not item:raise HTTPException(404,"Order not found")
    try:await service.request_cancel(item)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return {"success":True,"order_id":item.id,"status":item.status}
@app.delete("/orders/{order_id}")
async def cancel_delete(order_id:str):return await cancel_order(order_id)
@app.post("/orders/{order_id}/cancel")
async def cancel_post(order_id:str):return await cancel_order(order_id)
@app.get("/positions")
async def positions():
    items=[x for x in service.positions.values() if x.status!="CLOSED"]
    return {"positions":[{**x.model_dump(),"unrealized_pnl":x.unrealized()} for x in items]}

@app.get("/trading-configs")
async def trading_configs(x_user_id:str=Header(default="local")):
    rows=await service.db.fetch("""SELECT symbol,mode,status,config,created_at,updated_at FROM trading_configs
      WHERE owner_id=$1 OR owner_id IS NULL ORDER BY symbol""",x_user_id)
    return {"configs":[dict(row) for row in rows]}

@app.post("/trading-configs",status_code=201)
async def save_trading_config(request: TradingConfigCreate,x_user_id:str=Header(default="local")):
    symbol=request.symbol.strip().upper()
    if not symbol: raise HTTPException(422,"symbol must not be empty")
    mode=request.normalized_mode
    if mode not in {"PAPER","DEMO","PRODUCTION"}:raise HTTPException(422,"mode must be PAPER, DEMO or PRODUCTION")
    if any(item.symbol==symbol and item.status in {"PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","CANCEL_REQUESTED","UNKNOWN"} for item in service.orders.values()) or any(item.symbol==symbol and item.status!="CLOSED" for item in service.positions.values()):
        raise HTTPException(409,"Finish the existing trade before changing this asset")
    owner=await service.db.fetchval("SELECT owner_id FROM trading_configs WHERE symbol=$1",symbol)
    if owner is not None and owner!=x_user_id:raise HTTPException(409,"Trading asset belongs to another user")
    existing=await service.db.fetchrow("SELECT mode,config FROM trading_configs WHERE symbol=$1",symbol)
    previous=decode_json(existing["config"]) if existing else {}
    def value(config,camel,snake,default=None):return config.get(camel,config.get(snake,default))
    allocated=value(previous,"portfolioCapitalMode","portfolio_capital_mode")=="ALLOCATED"
    if allocated or value(request.config,"portfolioCapitalMode","portfolio_capital_mode")=="ALLOCATED":
        protected=(("portfolioCapitalMode","portfolio_capital_mode"),("portfolioId","portfolio_id"),
                   ("portfolioAllocationPercent","portfolio_allocation_percent"),
                   ("initialCapital","initial_capital"),("currentCapital","current_capital"))
        if (not allocated or mode!=existing["mode"] or
                any(value(previous,camel,snake)!=value(request.config,camel,snake) for camel,snake in protected)):
            raise HTTPException(409,"Change allocated portfolio capital, allocation or mode by reactivating the portfolio")
    try:
        await service.prepare_portfolio_assets([symbol])
        service.validate_live_config(request.config,mode)
        await service.validate_strategy_config(request.config)
        await service.validate_execution_mode(symbol,mode)
        capital=float(request.config.get("currentCapital",request.config.get("current_capital",
                      request.config.get("initialCapital",request.config.get("initial_capital",0)))))
        await service.validate_portfolio_capital(mode,capital)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    config={**request.config,"activationId":str(uuid4()),"activatedAt":int(time()*1000)}
    row=await service.db.fetchrow("""INSERT INTO trading_configs(symbol,mode,status,config,owner_id) VALUES($1,$2,'ACTIVE',$3::jsonb,$4)
      ON CONFLICT(symbol) DO UPDATE SET mode=excluded.mode,status='ACTIVE',config=excluded.config,
        owner_id=excluded.owner_id,updated_at=now()
      WHERE trading_configs.owner_id IS NULL OR trading_configs.owner_id=excluded.owner_id
      RETURNING symbol,mode,status,config,created_at,updated_at""",symbol,mode,json.dumps(config),x_user_id)
    if not row:raise HTTPException(409,"Trading asset belongs to another user")
    await service.publish_channel("trading.config","trading.config.saved",{"symbol":symbol,"mode":mode})
    return dict(row)
@app.delete("/trading-configs/{symbol}")
async def delete_trading_config(symbol: str,x_user_id:str=Header(default="local")):
    symbol=symbol.strip().upper()
    if not symbol:raise HTTPException(422,"symbol must not be empty")
    removed=await service.db.fetchval("""UPDATE trading_configs SET status='INACTIVE',updated_at=now()
      WHERE symbol=$1 AND status='ACTIVE' AND (owner_id=$2 OR owner_id IS NULL) RETURNING symbol""",symbol,x_user_id)
    if not removed:raise HTTPException(404,"Trading asset not found")
    await service.db.execute("DELETE FROM elliott_history_snapshots WHERE symbol=$1",symbol)
    try:await service.publish_channel("trading.config","trading.config.deleted",{"symbol":symbol})
    except Exception:log.exception("Asset stop event will be recovered by backend polling")
    pending_orders=[order for order in service.orders.values() if order.symbol==symbol and order.status in {
      "PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","UNKNOWN"}]
    pending_positions=[position for position in service.positions.values() if position.symbol==symbol and position.status!="CLOSED"]
    for order in pending_orders:
        try:await service.request_cancel(order)
        except Exception:log.exception("Order cancellation will be retried by backend supervisor")
    for position in pending_positions:
        try:
            if position.execution_mode=="PAPER":await service.close(position,position.quantity,position.current_price,"ASSET_REMOVED")
            else:await service.request_position_close(position,position.quantity,"ASSET_REMOVED")
        except Exception:log.exception("Position exit will be retried by backend supervisor")
    return {"success":True,"symbol":removed,"status":"STOPPING" if pending_orders or pending_positions else "STOPPED",
            "pending_orders":len(pending_orders),"pending_positions":len(pending_positions)}

@app.get("/portfolios")
async def portfolios(x_user_id:str=Header(default="local")):
    rows=await service.db.fetch("SELECT id,name,description,assets,created_at,updated_at FROM portfolios WHERE owner_id=$1 ORDER BY updated_at DESC",x_user_id)
    return {"portfolios":[portfolio_record(row) for row in rows]}

async def validated_portfolio_assets(request:PortfolioWrite,x_user_id:str):
    symbols=[item.symbol.strip().upper() for item in request.assets]
    if len(set(symbols))!=len(symbols):raise HTTPException(422,"Portfolio symbols must be unique")
    ids=[item.configuration_id for item in request.assets]
    rows=await service.db.fetch("SELECT id,config FROM strategy_configurations WHERE owner_id=$1 AND id=ANY($2::uuid[])",x_user_id,ids)
    configs={row["id"]:decode_json(row["config"]) for row in rows}
    if len(configs)!=len(set(ids)):raise HTTPException(422,"One or more configurations are unavailable")
    return [{"symbol":symbol,"configuration_id":str(item.configuration_id),"allocation_percent":item.allocation_percent,
             "config":configs[item.configuration_id]} for symbol,item in zip(symbols,request.assets)]

@app.post("/portfolios",status_code=201)
async def create_portfolio(request:PortfolioWrite,x_user_id:str=Header(default="local")):
    assets=await validated_portfolio_assets(request,x_user_id);name=request.name.strip()
    if not name:raise HTTPException(422,"name must not be empty")
    try:row=await service.db.fetchrow("""INSERT INTO portfolios(id,owner_id,name,description,assets) VALUES($1::uuid,$2,$3,$4,$5::jsonb)
      RETURNING id,name,description,assets,created_at,updated_at""",str(uuid4()),x_user_id,name,request.description.strip(),json.dumps(assets))
    except asyncpg.UniqueViolationError as exc:raise HTTPException(409,"Portfolio name already exists") from exc
    return portfolio_record(row)

@app.put("/portfolios/{portfolio_id}")
async def update_portfolio(portfolio_id:UUID,request:PortfolioWrite,x_user_id:str=Header(default="local")):
    assets=await validated_portfolio_assets(request,x_user_id);name=request.name.strip()
    try:row=await service.db.fetchrow("""UPDATE portfolios SET name=$3,description=$4,assets=$5::jsonb,updated_at=now()
      WHERE id=$1 AND owner_id=$2 RETURNING id,name,description,assets,created_at,updated_at""",
      portfolio_id,x_user_id,name,request.description.strip(),json.dumps(assets))
    except asyncpg.UniqueViolationError as exc:raise HTTPException(409,"Portfolio name already exists") from exc
    if not row:raise HTTPException(404,"Portfolio not found")
    return portfolio_record(row)

@app.delete("/portfolios/{portfolio_id}")
async def delete_portfolio(portfolio_id:UUID,x_user_id:str=Header(default="local")):
    rows=await service.db.fetch("""SELECT symbol FROM trading_configs WHERE coalesce(config->>'portfolioId',config->>'portfolio_id')=$1
      AND status='ACTIVE' AND (owner_id=$2 OR owner_id IS NULL)""",str(portfolio_id),x_user_id)
    async with service.db.acquire() as connection:
      async with connection.transaction():
        removed=await connection.fetchval("DELETE FROM portfolios WHERE id=$1 AND owner_id=$2 RETURNING id",portfolio_id,x_user_id)
        if not removed:raise HTTPException(404,"Portfolio not found")
        await connection.execute("""UPDATE trading_configs SET status='INACTIVE',updated_at=now()
          WHERE coalesce(config->>'portfolioId',config->>'portfolio_id')=$1 AND (owner_id=$2 OR owner_id IS NULL)""",
          str(portfolio_id),x_user_id)
    for row in rows:
        await service.publish_channel("trading.config","trading.config.deleted",{"symbol":row["symbol"]})
    return {"deleted":True,"id":str(removed)}

@app.post("/portfolios/{portfolio_id}/live")
async def portfolio_to_live(portfolio_id:UUID,request:PortfolioLiveRequest,x_user_id:str=Header(default="local")):
    mode=request.mode.strip().upper()
    if mode not in {"PAPER","DEMO","PRODUCTION"}:raise HTTPException(422,"mode must be PAPER, DEMO or PRODUCTION")
    if any(item.status in {"PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","CANCEL_REQUESTED","UNKNOWN"} for item in service.orders.values()) or any(item.status!="CLOSED" for item in service.positions.values()):
        raise HTTPException(409,"Finish active trades before switching the live portfolio")
    row=await service.db.fetchrow("SELECT assets FROM portfolios WHERE id=$1 AND owner_id=$2",portfolio_id,x_user_id)
    if not row:raise HTTPException(404,"Portfolio not found")
    assets=decode_json(row["assets"])
    if request.capital_mode=="ALLOCATED" and sum(float(item["allocation_percent"]) for item in assets)>100.000001:
        raise HTTPException(422,"Live portfolio allocation must not exceed 100%")
    symbols=[item["symbol"].strip().upper() for item in assets]
    conflicts=await service.db.fetch("""SELECT symbol FROM trading_configs WHERE symbol=ANY($1::text[])
      AND owner_id IS NOT NULL AND owner_id<>$2""",symbols,x_user_id)
    if conflicts:raise HTTPException(409,"Trading asset belongs to another user")
    try:await service.prepare_portfolio_assets(symbols)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    registered=await service.db.fetch(
        "SELECT symbol FROM trading_assets WHERE symbol=ANY($1::text[]) AND enabled AND validation_status='ACTIVE'",
        symbols,
    )
    registered_symbols={item["symbol"] for item in registered}
    unavailable=[symbol for symbol in symbols if symbol not in registered_symbols]
    if unavailable:
        raise HTTPException(409,f"Trading asset metadata is unavailable: {', '.join(unavailable)}")
    try:await service.validate_portfolio_capital(mode,request.capital)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    live_configs=[];activation_id=str(uuid4());activated_at=int(time()*1000)
    for item in assets:
        asset_capital=request.capital*float(item["allocation_percent"])/100 if request.capital_mode=="ALLOCATED" else request.capital
        config={**item["config"],"initialCapital":asset_capital,"currentCapital":asset_capital,
                "portfolioAllocationPercent":item["allocation_percent"],"portfolioId":str(portfolio_id),
                "portfolioCapitalMode":request.capital_mode,
                "activationId":activation_id,"activatedAt":activated_at}
        config.pop("initial_capital",None);config.pop("current_capital",None)
        try:
            TradingConfigCreate(symbol=item["symbol"],mode=mode,config=config)
            service.validate_live_config(config,mode)
            await service.validate_strategy_config(config)
            await service.validate_execution_mode(item["symbol"],mode)
        except (ValueError,TypeError) as exc:raise HTTPException(409,str(exc)) from exc
        live_configs.append((item["symbol"],config))
    async with service.db.acquire() as connection:
      async with connection.transaction():
        await connection.execute("""UPDATE trading_configs SET status='INACTIVE',updated_at=now()
          WHERE status='ACTIVE' AND NOT (symbol=ANY($1::text[])) AND (owner_id=$2 OR owner_id IS NULL)""",symbols,x_user_id)
        for symbol,config in live_configs:
          result=await connection.execute("""INSERT INTO trading_configs(symbol,mode,status,config,owner_id) VALUES($1,$2,'ACTIVE',$3::jsonb,$4)
            ON CONFLICT(symbol) DO UPDATE SET mode=excluded.mode,status='ACTIVE',config=excluded.config,
              owner_id=excluded.owner_id,updated_at=now()
            WHERE trading_configs.owner_id IS NULL OR trading_configs.owner_id=excluded.owner_id""",
            symbol,mode,json.dumps(config),x_user_id)
          if result=="INSERT 0 0":raise HTTPException(409,"Trading asset belongs to another user")
    for symbol,_ in live_configs:
        await service.publish_channel("trading.config","trading.config.saved",{
            "symbol":symbol,"mode":mode,"portfolio_id":str(portfolio_id),
        })
    return {"id":str(portfolio_id),"mode":mode,"capital":request.capital,"capital_mode":request.capital_mode,
            "activated_symbols":[symbol for symbol,_ in live_configs]}
@app.get("/configuration-library")
async def configuration_library(x_user_id:str=Header(default="local")):
    rows=await service.db.fetch("SELECT id,name,description,config,created_at,updated_at FROM strategy_configurations WHERE owner_id=$1 ORDER BY updated_at DESC",x_user_id)
    return {"configurations":[configuration_record(row) for row in rows]}
@app.post("/configuration-library",status_code=201)
async def create_configuration(request:StrategyConfigurationWrite,x_user_id:str=Header(default="local")):
    name=request.name.strip();description=request.description.strip()
    if not name:raise HTTPException(422,"name must not be empty")
    try:
        row=await service.db.fetchrow("""INSERT INTO strategy_configurations(id,owner_id,name,description,config)
          VALUES($1::uuid,$2,$3,$4,$5::jsonb) RETURNING id,name,description,config,created_at,updated_at""",
          str(uuid4()),x_user_id,name,description,json.dumps(request.config))
    except Exception as exc:
        if isinstance(exc,asyncpg.UniqueViolationError):raise HTTPException(409,"Configuration name already exists") from exc
        raise
    return configuration_record(row)
@app.put("/configuration-library/{configuration_id}")
async def update_configuration(configuration_id:UUID,request:StrategyConfigurationWrite,x_user_id:str=Header(default="local")):
    name=request.name.strip();description=request.description.strip()
    if not name:raise HTTPException(422,"name must not be empty")
    try:
        row=await service.db.fetchrow("""UPDATE strategy_configurations SET name=$3,description=$4,config=$5::jsonb,updated_at=now()
          WHERE id=$1 AND owner_id=$2 RETURNING id,name,description,config,created_at,updated_at""",
          configuration_id,x_user_id,name,description,json.dumps(request.config))
    except Exception as exc:
        if isinstance(exc,asyncpg.UniqueViolationError):raise HTTPException(409,"Configuration name already exists") from exc
        raise
    if not row:raise HTTPException(404,"Configuration not found")
    return configuration_record(row)
@app.delete("/configuration-library/{configuration_id}")
async def delete_configuration(configuration_id:UUID,x_user_id:str=Header(default="local")):
    removed=await service.db.fetchval("DELETE FROM strategy_configurations WHERE id=$1 AND owner_id=$2 RETURNING id",configuration_id,x_user_id)
    if not removed:raise HTTPException(404,"Configuration not found")
    return {"success":True,"id":str(removed)}
@app.get("/positions/{position_id}")
async def position(position_id:str):
    item=service.positions.get(position_id)
    if not item:raise HTTPException(404,"Position not found")
    return item
@app.post("/positions/{position_id}/close")
async def close_position(position_id:str,request:CloseRequest):
    item=service.positions.get(position_id)
    if not item or item.status=="CLOSED":raise HTTPException(404,"Open position not found")
    if item.execution_mode!="PAPER":
        order=await service.request_position_close(item,request.quantity or item.quantity,request.reason)
        return {"success":True,"accepted":True,"order_id":order.id,"status":order.status,
                "closed_quantity":0,"remaining_quantity":item.quantity,"pnl":0}
    qty,remaining,pnl=await service.close(item,request.quantity or item.quantity,item.current_price,request.reason)
    return {"success":True,"closed_quantity":qty,"remaining_quantity":remaining,"pnl":pnl}
@app.get("/trades")
@app.get("/trades/history")
async def trades(symbol:str|None=None,limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
    rows=await service.db.fetch("SELECT data FROM closed_trades WHERE data->>'strategy'='ELLIOTT' AND ($1::text IS NULL OR symbol=$1) ORDER BY closed_at DESC LIMIT $2 OFFSET $3",symbol.upper() if symbol else None,limit,offset)
    total=await service.db.fetchval("SELECT count(*) FROM closed_trades WHERE data->>'strategy'='ELLIOTT' AND ($1::text IS NULL OR symbol=$1)",symbol.upper() if symbol else None)
    return {"trades":[decode_json(r["data"]) for r in rows],"total":total}
@app.get("/trades/assets")
async def trade_assets():
    rows=await service.db.fetch("""
      SELECT asset.symbol,count(ct.id) AS trades_count
      FROM (
        SELECT symbol FROM trading_configs
        WHERE status='ACTIVE' AND upper(config->>'strategy')='ELLIOTT'
        UNION
        SELECT symbol FROM closed_trades WHERE data->>'strategy'='ELLIOTT'
      ) asset
      LEFT JOIN closed_trades ct ON ct.symbol=asset.symbol AND ct.data->>'strategy'='ELLIOTT'
      GROUP BY asset.symbol ORDER BY asset.symbol
    """)
    return {"assets":[{"symbol":row["symbol"],"trades_count":row["trades_count"]} for row in rows]}
@app.get("/trades/statistics")
async def statistics(symbol:str|None=None):
    rows=await service.db.fetch("SELECT pnl::float8,data FROM closed_trades WHERE data->>'strategy'='ELLIOTT' AND ($1::text IS NULL OR symbol=$1)",symbol.upper() if symbol else None);pnls=[r["pnl"] for r in rows];wins=[x for x in pnls if x>0];losses=[x for x in pnls if x<0]
    return {"total_trades":len(pnls),"win_rate":len(wins)/len(pnls)*100 if pnls else 0,"profit_factor":sum(wins)/abs(sum(losses)) if losses else None,"avg_profit":sum(wins)/len(wins) if wins else 0,"avg_loss":sum(losses)/len(losses) if losses else 0,"avg_duration":sum(decode_json(r["data"]).get("duration_seconds",0) for r in rows)/len(rows) if rows else 0,"max_drawdown":min([0,*pnls])}
@app.get("/trades/analysis")
async def trade_analysis(symbol:str|None=None):
    rows=await service.db.fetch("SELECT data FROM closed_trades WHERE data->>'strategy'='ELLIOTT' AND ($1::text IS NULL OR symbol=$1) ORDER BY closed_at DESC",symbol.upper() if symbol else None)
    return analyze_trades([decode_json(row["data"]) for row in rows])
@app.get("/trades/{trade_id}")
async def trade(trade_id:str):
    row=await service.db.fetchrow("SELECT data FROM closed_trades WHERE id=$1::uuid AND data->>'strategy'='ELLIOTT'",trade_id)
    if not row:raise HTTPException(404,"Trade not found")
    return decode_json(row["data"])
