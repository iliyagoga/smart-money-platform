from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Query
from .infrastructure import Infrastructure
from .models import *
from .service import SMCService
from .scenarios import ScenarioTemplate
from .settings import settings

infra=Infrastructure(settings.database_url,settings.redis_url)
service=SMCService(infra,settings.swing_lookback)
class RebuildRequest(BaseModel):
    symbol:str;timeframes:list[Timeframe];limit:int=Field(default=500,ge=100,le=2000)

@asynccontextmanager
async def lifespan(app:FastAPI):
    await infra.connect();await service.start()
    yield
    await service.stop();await infra.close()

app=FastAPI(title="Smart Money Service",version="1.0.0",lifespan=lifespan)

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

@app.get("/smart-money/swings")
async def swings(symbol:str,timeframe:Timeframe,limit:int=Query(100,ge=1,le=1000)):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"swings":service.pipeline.swings[key][-limit:]}

@app.get("/smart-money/order-blocks")
async def order_blocks(symbol:str,timeframe:Timeframe):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"order_blocks":[x for x in service.pipeline.obs[key] if not x.is_broken]}

@app.get("/smart-money/fvg")
async def fvgs(symbol:str,timeframe:Timeframe):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"fvgs":[x for x in service.pipeline.fvgs[key] if not x.is_filled]}

@app.get("/smart-money/liquidity")
async def liquidity(symbol:str,timeframe:Timeframe):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"liquidity_zones":[x for x in service.pipeline.liquidity[key] if not x.swept]}

@app.get("/smart-money/bos")
async def bos(symbol:str,timeframe:Timeframe,limit:int=Query(100,ge=1,le=1000)):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"bos":[x for x in service.pipeline.changes[key] if x.type=="BOS"][-limit:]}

@app.get("/smart-money/choch")
async def choch(symbol:str,timeframe:Timeframe,limit:int=Query(100,ge=1,le=1000)):
    key=state(symbol,timeframe);return {"symbol":key[0],"timeframe":timeframe,"choch":[x for x in service.pipeline.changes[key] if x.type=="CHOCH"][-limit:]}

@app.get("/smart-money/structure")
async def structure(symbol:str,timeframe:Timeframe):
    key=state(symbol,timeframe);sw=service.pipeline.swings[key]
    high=next((x.price for x in reversed(sw) if x.type==SwingType.HIGH),None);low=next((x.price for x in reversed(sw) if x.type==SwingType.LOW),None)
    return {"symbol":key[0],"timeframe":timeframe,"last_swing_high":high,"last_swing_low":low,"trend":service.pipeline.trends.get(key),
      "order_blocks":[x for x in service.pipeline.obs[key] if not x.is_broken],"fvgs":[x for x in service.pipeline.fvgs[key] if not x.is_filled],"liquidity_zones":[x for x in service.pipeline.liquidity[key] if not x.swept]}

@app.get("/smart-money/context")
async def context(symbol:str):
    symbol=symbol.strip().upper();trends=[v for (s,_),v in service.pipeline.trends.items() if s==symbol and v]
    up=sum(x.strength for x in trends if x.direction==TrendDirection.UP);down=sum(x.strength for x in trends if x.direction==TrendDirection.DOWN);total=sum(x.strength for x in trends) or 1
    regime="TRENDING_UP" if up>down and up/total>=.6 else "TRENDING_DOWN" if down>up and down/total>=.6 else "RANGING"
    return {"symbol":symbol,"regime":regime,"confidence":max(up,down)/total,"adx":None,"volatility":None}

@app.get("/scenarios")
async def scenarios(symbol:str|None=None,status:str|None=None,limit:int=Query(100,ge=1,le=1000)):
    items=service.scenarios.list(symbol,status);return {"scenarios":items[-limit:],"total":len(items)}

@app.get("/scenario-templates")
async def scenario_templates(enabled_only:bool=False):
    items=service.scenarios.store.list(enabled_only);return {"templates":items,"total":len(items)}

@app.get("/scenario-templates/{template_id}")
async def scenario_template(template_id:str):
    item=service.scenarios.store.get(template_id)
    if not item:raise HTTPException(404,"Scenario template not found")
    return item

@app.put("/scenario-templates/{template_id}")
async def save_scenario_template(template_id:str,template:ScenarioTemplate):
    if template.id!=template_id.upper():raise HTTPException(422,"Template id does not match path")
    return service.scenarios.store.save(template)

@app.delete("/scenario-templates/{template_id}")
async def delete_scenario_template(template_id:str):
    if not service.scenarios.store.delete(template_id):raise HTTPException(404,"Scenario template not found")
    return {"success":True,"id":template_id.upper()}

@app.get("/scenarios/{scenario_id}")
async def scenario(scenario_id:str):
    item=next((x for x in service.scenarios.items.values() if x.id==scenario_id),None)
    if not item:raise HTTPException(404,"Scenario not found")
    return item

@app.post("/scenarios/{scenario_id}/recalculate")
async def recalculate(scenario_id:str):
    item=next((x for x in service.scenarios.items.values() if x.id==scenario_id),None)
    if not item:raise HTTPException(404,"Scenario not found")
    return {"updated":True,"confidence":item.confidence}
