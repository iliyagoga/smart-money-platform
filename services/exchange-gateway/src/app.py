from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Query
from pydantic import BaseModel
from .okx import TIMEFRAMES
from .service import ExchangeGateway
from .settings import settings
service=ExchangeGateway(settings)
@asynccontextmanager
async def lifespan(app):await service.start();yield;await service.stop()
app=FastAPI(title="OKX Exchange Gateway",version="1.0.0",lifespan=lifespan)
class SyncRequest(BaseModel):symbol:str="BTC-USDT-SWAP";timeframe:str="M15";limit:int=100
@app.get("/health")
async def health():return {"status":"UP","market_data_enabled":settings.market_data_enabled,"connections":service.connected,"demo":settings.okx_demo,"last_error":service.last_error}
@app.post("/exchange/sync")
async def sync(req:SyncRequest):
    req.symbol=req.symbol.upper();req.timeframe=req.timeframe.upper()
    if req.timeframe not in TIMEFRAMES:raise HTTPException(422,"Unsupported timeframe")
    try:return {"ingested":await service.history(req.symbol,req.timeframe,req.limit)}
    except Exception as exc:raise HTTPException(502,str(exc)) from exc
@app.get("/exchange/account/balance")
async def balance():
    try:return {"balances":await service.private("GET","/api/v5/account/balance")}
    except ValueError as exc:raise HTTPException(503,str(exc)) from exc

