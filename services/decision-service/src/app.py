from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException
from .models import *
from .service import DecisionService
from .settings import settings

service=DecisionService(settings.database_url,settings.redis_url,settings.confidence_threshold,settings.conflict_min_delta,settings.default_capital)
@asynccontextmanager
async def lifespan(app):
    await service.start();yield;await service.stop()
app=FastAPI(title="Decision and Risk Service",version="1.0.0",lifespan=lifespan)

@app.get("/health")
async def health():
    try:await service.redis.ping();await service.db.fetchval("SELECT 1");return {"status":"UP"}
    except Exception as exc:raise HTTPException(503,"Dependency unavailable") from exc
@app.get("/risk/config",response_model=RiskConfig)
async def risk_config():return await service.config()
@app.patch("/risk/config")
async def patch_risk(patch:RiskConfigPatch):return {"updated":True,"config":await service.update_config(patch)}
@app.post("/risk/calculate")
async def risk_calculate(request:RiskCalculateRequest):
    signal=service.signals.get(request.signal_id)
    if not signal:
        row=await service.db.fetchrow("SELECT data FROM trade_signals WHERE id=$1::uuid",request.signal_id)
        if not row:raise HTTPException(404,"Signal not found")
        signal=TradeSignal.model_validate(row["data"])
    return await service.assess(signal,request.capital)
@app.post("/internal/scenarios/evaluate")
async def evaluate(scenario:Scenario):return await service.evaluate(scenario)
@app.post("/signals/simulate-elliott",status_code=201)
async def simulate_elliott(request:SimulatedElliottSignalRequest):
    try:return await service.simulate_elliott(request)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
