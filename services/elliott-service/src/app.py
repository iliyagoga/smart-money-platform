from contextlib import asynccontextmanager
import asyncio
import json
from fastapi import FastAPI,HTTPException,Query
from .infrastructure import Infrastructure
from .models import *
from .service import ElliottService
from .elliott_live import normalize_config
from .settings import settings

infra=Infrastructure(settings.database_url,settings.redis_url)
service=ElliottService(infra)
elliott_history_cache={}
elliott_history_inflight={}
class RebuildRequest(BaseModel):
    symbol:str;timeframes:list[Timeframe];limit:int=Field(default=500,ge=100,le=2000)
class ElliottHistoryRequest(BaseModel):
    symbol:str
    candles_by_timeframe:dict[Timeframe,list[Candle]]

@asynccontextmanager
async def lifespan(app:FastAPI):
    await infra.connect();await service.start()
    yield
    await service.stop();await infra.close()

app=FastAPI(title="Elliott Service",version="1.0.0",lifespan=lifespan)

def state(symbol:str,timeframe:Timeframe):return (symbol.strip().upper(),timeframe)

@app.get("/health")
async def health():
    try:await infra.redis.ping();await infra.db.fetchval("SELECT 1");return {"status":"UP"}
    except Exception as exc:raise HTTPException(503,"Dependency unavailable") from exc

@app.post("/internal/analyze")
async def analyze(candle:Candle):return await service.process(candle)

@app.post("/internal/rebuild")
async def rebuild(request:RebuildRequest):
    return await service.rebuild(request.symbol,request.timeframes,request.limit)

@app.get("/elliott/patterns")
async def elliott_patterns(symbol:str):
    symbol=symbol.strip().upper()
    items=service.elliott.latest_patterns.get(symbol,[])
    return {"symbol":symbol,"patterns":items,"total":len(items)}

@app.get("/elliott/entries")
async def elliott_entries(symbol:str):
    symbol=symbol.strip().upper()
    items=service.elliott.latest_entries.get(symbol,[])
    return {"symbol":symbol,"entries":items,"total":len(items)}

@app.post("/elliott/history")
async def elliott_history(request:ElliottHistoryRequest):
    from .elliott_live import ElliottLiveEngine
    symbol=request.symbol.strip().upper()
    config=await service.trading_config(symbol)
    if not config:raise HTTPException(404,"Active trading config not found")
    normalized=normalize_config(config);elliott=normalized.get("elliott",{})
    try:entry_timeframe=Timeframe(elliott["entry_timeframe"])
    except (KeyError,ValueError) as exc:raise HTTPException(422,"Invalid Elliott entry timeframe") from exc
    mapping={(symbol,timeframe):items for timeframe,items in request.candles_by_timeframe.items()}
    entry=mapping.get((symbol,entry_timeframe),[])
    if not entry:raise HTTPException(422,"Entry timeframe candles are required")
    fingerprint=tuple(sorted((str(timeframe),len(items),items[0].timestamp if items else 0,
                              items[-1].timestamp if items else 0,items[-1].open if items else 0,
                              items[-1].high if items else 0,items[-1].low if items else 0,
                              items[-1].close if items else 0)
                             for timeframe,items in request.candles_by_timeframe.items()))
    cache_key=(symbol,json.dumps(config,sort_keys=True,separators=(",",":")),fingerprint)
    if cache_key in elliott_history_cache:return elliott_history_cache[cache_key]
    async def calculate():
        engine=ElliottLiveEngine(live_signal_ids=set(service.elliott.live_signal_ids))
        await asyncio.to_thread(engine.generate,symbol,entry[-1],mapping,config,False)
        patterns=engine.latest_patterns.get(symbol,[]);entries=engine.latest_entries.get(symbol,[])
        return {"symbol":symbol,"patterns":patterns,"entries":entries,
                "patterns_total":len(patterns),"entries_total":len(entries)}
    task=elliott_history_inflight.get(cache_key)
    owner=task is None
    if owner:
        task=asyncio.create_task(calculate());elliott_history_inflight[cache_key]=task
    try:result=await task
    finally:
        if owner:elliott_history_inflight.pop(cache_key,None)
    elliott_history_cache[cache_key]=result
    if len(elliott_history_cache)>128:
        for stale in list(elliott_history_cache)[:-64]:elliott_history_cache.pop(stale,None)
    return result

