from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Query
from .infrastructure import Infrastructure
from .models import *
from .service import ElliottService
from .settings import settings

infra=Infrastructure(settings.database_url,settings.redis_url)
service=ElliottService(infra)
class RebuildRequest(BaseModel):
    symbol:str;timeframes:list[Timeframe];limit:int=Field(default=500,ge=100,le=2000)

@asynccontextmanager
async def lifespan(app:FastAPI):
    await infra.connect();await service.start()
    yield
    await service.stop();await infra.close()

app=FastAPI(title="Elliott Wave Service",version="1.0.0",lifespan=lifespan)

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
    items=list(service.elliott.latest_entries.get(symbol,[]))
    rows=await infra.db.fetch("""SELECT data FROM scenarios WHERE symbol=$1
      AND data @> '{"objects_used":[{"kind":"ELLIOTT_SIMULATION"}]}'::jsonb
      ORDER BY created_at DESC LIMIT 100""",symbol)
    for row in rows:
        value=json.loads(row["data"]) if isinstance(row["data"],str) else dict(row["data"])
        items.append({
            "id":value["id"],"direction":value["direction"],"setup_type":value["setup_type"],
            "status":value.get("status","SELECTED"),"entry_type":value.get("entry_type","MARKET"),
            "entry_zone_low":value["entry_zone_low"],"entry_zone_high":value["entry_zone_high"],
            "created_at":value["created_at"],"expires_at":value["expires_at"],
            "entry_model":"SIMULATION","origin":"LIVE","stop_loss_price":value.get("stop_loss_price"),
            "take_profit_prices":value.get("take_profit_prices",[]),
        })
    items=list({item["id"]:item for item in items}.values())
    return {"symbol":symbol,"entries":items,"total":len(items)}

@app.get("/elliott/history")
async def elliott_history(symbol:str):return await service.history_snapshot(symbol)

@app.post("/internal/history/rebuild")
async def rebuild_elliott_history(symbol:str):
    result=await service.rebuild_history_snapshot(symbol)
    if result is None:raise HTTPException(404,"Active trading config not found or replay failed")
    return await service.history_snapshot(symbol)

@app.get("/scenarios")
async def scenarios(symbol:str|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=1000)):
    items=[item for item in service.scenarios.values() if (symbol is None or item.symbol==symbol.strip().upper()) and (status is None or item.status==status)];return {"scenarios":items[-limit:],"total":len(items)}

@app.get("/scenarios/{scenario_id}")
async def scenario(scenario_id:str):
    item=next((x for x in service.scenarios.values() if x.id==scenario_id),None)
    if not item:raise HTTPException(404,"Scenario not found")
    return item
