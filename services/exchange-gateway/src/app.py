from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
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
    symbol:str="BTC-USDT-SWAP";timeframes:list[str]=["M1","M5","M15","H1","H4","D1"]
    from_timestamp:int|None=Field(default=None,ge=0);to_timestamp:int|None=Field(default=None,ge=0)
    max_candles_per_timeframe:int=Field(default=10000,ge=1,le=1000000)
    @model_validator(mode="after")
    def normalize(self):
        self.symbol=self.symbol.strip().upper();self.timeframes=list(dict.fromkeys(x.strip().upper() for x in self.timeframes))
        if not self.timeframes or any(x not in TIMEFRAMES for x in self.timeframes):raise ValueError("Unsupported timeframe")
        if self.from_timestamp is not None and self.to_timestamp is not None and self.from_timestamp>=self.to_timestamp:
            raise ValueError("from_timestamp must be earlier than to_timestamp")
        return self
@app.get("/health")
async def health():return {"status":"UP","market_data_enabled":settings.market_data_enabled,"connections":service.connected,"symbols":service.symbols,"demo":settings.okx_demo,"last_error":service.last_error}
@app.post("/exchange/reload-symbols")
async def reload_symbols():return {"symbols":await service.refresh_symbols()}
@app.post("/exchange/sync")
async def sync(req:SyncRequest):
    req.symbol=req.symbol.upper();req.timeframe=req.timeframe.upper()
    if req.timeframe not in TIMEFRAMES:raise HTTPException(422,"Unsupported timeframe")
    try:return {"ingested":await service.history(req.symbol,req.timeframe,req.limit)}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@app.post("/exchange/history",status_code=202)
async def history(req:HistoryRequest):
    job_id=str(uuid4());return await service.create_history(
        job_id,req.symbol,req.timeframes,req.from_timestamp,req.to_timestamp,req.max_candles_per_timeframe,
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
