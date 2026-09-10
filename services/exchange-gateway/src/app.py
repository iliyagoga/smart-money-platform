from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Query
from pydantic import BaseModel,Field,model_validator
from uuid import uuid4
from .okx import TIMEFRAMES
from .service import ExchangeGateway
from .settings import settings
service=ExchangeGateway(settings)
@asynccontextmanager
async def lifespan(app):await service.start();yield;await service.stop()
app=FastAPI(title="OKX Exchange Gateway",version="1.0.0",lifespan=lifespan)
class SyncRequest(BaseModel):symbol:str="BTC-USDT-SWAP";timeframe:str="M15";limit:int=100
class HistoryRequest(BaseModel):
    symbol:str="BTC-USDT-SWAP";timeframes:list[str]=["M1","M5","M15","M30","H1","H4","D1"]
    from_timestamp:int|None=Field(default=None,ge=0);to_timestamp:int|None=Field(default=None,ge=0)
    incremental:bool=False
    backfill:bool=False
    @model_validator(mode="after")
    def normalize(self):
        self.symbol=self.symbol.strip().upper();self.timeframes=list(dict.fromkeys(x.strip().upper() for x in self.timeframes))
        if not self.timeframes or any(x not in TIMEFRAMES for x in self.timeframes):raise ValueError("Unsupported timeframe")
        if self.from_timestamp is not None and self.to_timestamp is not None and self.from_timestamp>=self.to_timestamp:
            raise ValueError("from_timestamp must be earlier than to_timestamp")
        return self
@app.get("/health")
async def health():return {"status":"UP","market_data_enabled":settings.market_data_enabled,"trading_enabled":settings.trading_enabled,"connections":service.connected,"symbols":service.symbols,"demo":settings.okx_demo,"last_error":service.last_error}
@app.post("/exchange/reload-symbols")
async def reload_symbols():return {"symbols":await service.refresh_symbols()}
@app.get("/exchange/instruments")
async def instruments():return {"instruments":await service.instruments()}
@app.get("/exchange/instruments/{symbol}/availability")
async def instrument_availability(symbol:str,mode:str="DEMO"):
    return await service.instrument_availability(symbol.strip().upper(),mode)
@app.post("/exchange/sync")
async def sync(req:SyncRequest):
    req.symbol=req.symbol.upper();req.timeframe=req.timeframe.upper()
    if req.timeframe not in TIMEFRAMES:raise HTTPException(422,"Unsupported timeframe")
    try:return {"ingested":await service.history(req.symbol,req.timeframe,req.limit)}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@app.get("/exchange/market-candles")
async def market_candles(symbol:str, timeframe:str="M15", limit:int=Query(default=300,ge=1,le=300),
                         after:int|None=Query(default=None,ge=0)):
    symbol=symbol.strip().upper(); timeframe=timeframe.strip().upper()
    if timeframe not in TIMEFRAMES: raise HTTPException(422,"Unsupported timeframe")
    try: return {"symbol":symbol,"timeframe":timeframe,
                 "candles":await service.market_candles(symbol,timeframe,limit,after)}
    except Exception as exc: raise HTTPException(502,str(exc)) from exc
@app.post("/exchange/history",status_code=202)
async def history(req:HistoryRequest):
    job_id=str(uuid4());return await service.create_history(
        job_id,req.symbol,req.timeframes,req.from_timestamp,req.to_timestamp,req.incremental,req.backfill,
    )
@app.get("/exchange/history")
async def histories():return {"jobs":await service.history_jobs()}
@app.get("/exchange/history/{job_id}")
async def history_status(job_id:str):
    job=await service.history_job(job_id)
    if not job:raise HTTPException(404,"History job not found")
    return job
@app.post("/exchange/history/{job_id}/{action}")
async def history_control(job_id:str,action:str):
    if action not in {"pause","resume","cancel"}:raise HTTPException(422,"Unsupported action")
    job=await service.control_history(job_id,action)
    if not job:raise HTTPException(409,"Action is not allowed for current job state")
    return job
@app.get("/exchange/account/balance")
async def balance():
    try:return {"balances":await service.private("GET","/api/v5/account/balance")}
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc
@app.get("/exchange/orders")
async def exchange_orders(limit:int=Query(default=100,ge=1,le=1000)):
    return {"orders":await service.exchange_orders(limit)}
@app.post("/exchange/orders/{order_id}/cancel")
async def cancel_exchange_order(order_id:str):
    try:return await service.cancel_order(order_id)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
