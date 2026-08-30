from contextlib import asynccontextmanager
import json
from fastapi import FastAPI,HTTPException,Query
from .models import *
from .service import ExecutionService,decode_json
from .settings import settings
from pydantic import BaseModel

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
    has_order=any(item.symbol==symbol and item.status in {"PENDING","OPEN"} for item in service.orders.values())
    has_position=any(item.symbol==symbol and item.status!="CLOSED" for item in service.positions.values())
    if has_order or has_position:
        raise HTTPException(409,"Close the active order or position before removing the trading asset")
    removed=await service.db.fetchval("DELETE FROM trading_configs WHERE symbol=$1 RETURNING symbol",symbol)
    if not removed:raise HTTPException(404,"Trading asset not found")
    return {"success":True,"symbol":removed}
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
