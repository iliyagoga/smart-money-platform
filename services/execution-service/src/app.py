from contextlib import asynccontextmanager
import json
import asyncpg
from fastapi import FastAPI,Header,HTTPException,Query
from .models import *
from .service import ExecutionService,decode_json
from .settings import settings
from pydantic import BaseModel,Field
from uuid import UUID,uuid4

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

def configuration_record(row):
    value=dict(row);value["id"]=str(value["id"])
    value["config"]=decode_json(value["config"])
    value["created_at"]=value["created_at"].isoformat();value["updated_at"]=value["updated_at"].isoformat()
    return value

def portfolio_record(row):
    value=dict(row);value["id"]=str(value["id"]);value["assets"]=decode_json(value["assets"])
    value["created_at"]=value["created_at"].isoformat();value["updated_at"]=value["updated_at"].isoformat()
    return value

service=ExecutionService(settings.database_url,settings.redis_url,settings.stream_group,settings.consumer_name,settings.execution_mode)
@asynccontextmanager
async def lifespan(app):await service.start();yield;await service.stop()
app=FastAPI(title="Execution and Position Service",version="1.0.0",lifespan=lifespan)

@app.get("/health")
async def health():
    try:await service.redis.ping();await service.db.fetchval("SELECT 1");return {"status":"UP","mode":service.mode}
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
async def trading_configs():
    rows=await service.db.fetch("SELECT symbol,mode,status,config,created_at,updated_at FROM trading_configs ORDER BY symbol")
    return {"configs":[dict(row) for row in rows]}

@app.post("/trading-configs",status_code=201)
async def save_trading_config(request: TradingConfigCreate):
    symbol=request.symbol.strip().upper()
    if not symbol: raise HTTPException(422,"symbol must not be empty")
    mode=request.normalized_mode
    if mode not in {"PAPER","DEMO","PRODUCTION"}:raise HTTPException(422,"mode must be PAPER, DEMO or PRODUCTION")
    row=await service.db.fetchrow("""INSERT INTO trading_configs(symbol,mode,status,config) VALUES($1,$2,'ACTIVE',$3::jsonb)
      ON CONFLICT(symbol) DO UPDATE SET mode=excluded.mode,status='ACTIVE',config=excluded.config,updated_at=now()
      RETURNING symbol,mode,status,config,created_at,updated_at""",symbol,mode,json.dumps(request.config))
    return dict(row)
@app.delete("/trading-configs/{symbol}")
async def delete_trading_config(symbol: str):
    symbol=symbol.strip().upper()
    if not symbol:raise HTTPException(422,"symbol must not be empty")
    has_order=any(item.symbol==symbol and item.status in {"PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","CANCEL_REQUESTED"} for item in service.orders.values())
    has_position=any(item.symbol==symbol and item.status!="CLOSED" for item in service.positions.values())
    if has_order or has_position:
        raise HTTPException(409,"Close the active order or position before removing the trading asset")
    removed=await service.db.fetchval("DELETE FROM trading_configs WHERE symbol=$1 RETURNING symbol",symbol)
    if not removed:raise HTTPException(404,"Trading asset not found")
    return {"success":True,"symbol":removed}

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
    removed=await service.db.fetchval("DELETE FROM portfolios WHERE id=$1 AND owner_id=$2 RETURNING id",portfolio_id,x_user_id)
    if not removed:raise HTTPException(404,"Portfolio not found")
    return {"deleted":True,"id":str(removed)}

@app.post("/portfolios/{portfolio_id}/live")
async def portfolio_to_live(portfolio_id:UUID,request:PortfolioLiveRequest,x_user_id:str=Header(default="local")):
    mode=request.mode.strip().upper()
    if mode not in {"PAPER","DEMO","PRODUCTION"}:raise HTTPException(422,"mode must be PAPER, DEMO or PRODUCTION")
    row=await service.db.fetchrow("SELECT assets FROM portfolios WHERE id=$1 AND owner_id=$2",portfolio_id,x_user_id)
    if not row:raise HTTPException(404,"Portfolio not found")
    assets=decode_json(row["assets"])
    if sum(float(item["allocation_percent"]) for item in assets)>100.000001:
        raise HTTPException(422,"Live portfolio allocation must not exceed 100%")
    async with service.db.acquire() as connection:
      async with connection.transaction():
        for item in assets:
          config={**item["config"],"portfolioAllocationPercent":item["allocation_percent"],"portfolioId":str(portfolio_id)}
          await connection.execute("""INSERT INTO trading_configs(symbol,mode,status,config) VALUES($1,$2,'ACTIVE',$3::jsonb)
            ON CONFLICT(symbol) DO UPDATE SET mode=excluded.mode,status='ACTIVE',config=excluded.config,updated_at=now()""",
            item["symbol"],mode,json.dumps(config))
    return {"id":str(portfolio_id),"mode":mode,"activated_symbols":[item["symbol"] for item in assets]}
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
    qty,remaining,pnl=await service.close(item,request.quantity or item.quantity,request.price or item.current_price,request.reason)
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
