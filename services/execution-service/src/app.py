from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Query
from .models import *
from .service import ExecutionService,decode_json
from .settings import settings

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
    if data.type=="MARKET" and data.price is None:
        price=await service.db.fetchval("SELECT close::float8 FROM candles WHERE symbol=$1 ORDER BY ts DESC LIMIT 1",data.symbol)
        if price is None:raise HTTPException(422,"No market price available")
        data.price=price
    try:order=await service.create_order(Order(**data.model_dump()))
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return {"order_id":order.id,"status":order.status}
@app.get("/orders/{order_id}")
async def order(order_id:str):
    item=service.orders.get(order_id)
    if not item:raise HTTPException(404,"Order not found")
    return item
async def cancel_order(order_id:str):
    item=service.orders.get(order_id)
    if not item:raise HTTPException(404,"Order not found")
    if item.status=="FILLED":raise HTTPException(409,"Filled order cannot be cancelled")
    item.status="CANCELLED";await service.save_order(item);await service.publish("order.cancelled",{"order_id":item.id,"signal_id":item.signal_id,"reason":"MANUAL","timestamp":now_ms()});return {"success":True,"order_id":item.id}
@app.delete("/orders/{order_id}")
async def cancel_delete(order_id:str):return await cancel_order(order_id)
@app.post("/orders/{order_id}/cancel")
async def cancel_post(order_id:str):return await cancel_order(order_id)
@app.get("/positions")
async def positions():
    items=[x for x in service.positions.values() if x.status!="CLOSED"]
    return {"positions":[{**x.model_dump(),"unrealized_pnl":x.unrealized()} for x in items]}
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
    rows=await service.db.fetch("SELECT data FROM closed_trades WHERE ($1::text IS NULL OR symbol=$1) ORDER BY closed_at DESC LIMIT $2 OFFSET $3",symbol.upper() if symbol else None,limit,offset)
    total=await service.db.fetchval("SELECT count(*) FROM closed_trades WHERE ($1::text IS NULL OR symbol=$1)",symbol.upper() if symbol else None)
    return {"trades":[decode_json(r["data"]) for r in rows],"total":total}
@app.get("/trades/statistics")
async def statistics(symbol:str|None=None):
    rows=await service.db.fetch("SELECT pnl::float8,data FROM closed_trades WHERE ($1::text IS NULL OR symbol=$1)",symbol.upper() if symbol else None);pnls=[r["pnl"] for r in rows];wins=[x for x in pnls if x>0];losses=[x for x in pnls if x<0]
    return {"total_trades":len(pnls),"win_rate":len(wins)/len(pnls)*100 if pnls else 0,"profit_factor":sum(wins)/abs(sum(losses)) if losses else None,"avg_profit":sum(wins)/len(wins) if wins else 0,"avg_loss":sum(losses)/len(losses) if losses else 0,"avg_duration":sum(decode_json(r["data"]).get("duration_seconds",0) for r in rows)/len(rows) if rows else 0,"max_drawdown":min([0,*pnls])}
@app.get("/trades/{trade_id}")
async def trade(trade_id:str):
    row=await service.db.fetchrow("SELECT data FROM closed_trades WHERE id=$1::uuid",trade_id)
    if not row:raise HTTPException(404,"Trade not found")
    return decode_json(row["data"])
