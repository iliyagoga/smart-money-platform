from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from .service import LearningService, decode
from .settings import settings

service=LearningService(settings)
@asynccontextmanager
async def lifespan(app):
    await service.start(); yield; await service.stop()
app=FastAPI(title="Smart Money Learning Service",version="1.0.0",lifespan=lifespan)

@app.get("/health")
async def health(): return {"status":"UP"}
@app.get("/learning/samples")
async def samples(limit:int=Query(100,ge=1,le=1000),offset:int=Query(0,ge=0)):
    rows=await service.db.fetch("SELECT id,position_id,scenario_id,symbol,regime,template_id,features,outcome,extract(epoch from created_at)*1000 created_at FROM learning_samples ORDER BY created_at DESC LIMIT $1 OFFSET $2",limit,offset); total=await service.db.fetchval("SELECT count(*) FROM learning_samples"); return {"samples":[{**dict(r),"id":str(r["id"]),"position_id":str(r["position_id"]),"scenario_id":str(r["scenario_id"]) if r["scenario_id"] else None,"features":decode(r["features"]),"created_at":int(r["created_at"])} for r in rows],"total_count":total}
@app.get("/learning/models")
async def models():
    rows=await service.db.fetch("SELECT id,model_type type,version,path,metrics,training_samples_count samples_count,is_active,extract(epoch from training_date)*1000 training_date FROM model_versions ORDER BY training_date DESC"); return {"models":[{**dict(r),"id":str(r["id"]),"metrics":decode(r["metrics"]),"training_date":int(r["training_date"])} for r in rows]}
@app.post("/learning/train",status_code=202)
async def train():
    try:return await service.train()
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
@app.get("/learning/bandit")
async def bandit(regime:str|None=None):
    rows=await service.db.fetch("SELECT regime,template_id,successes,failures,extract(epoch from last_updated)*1000 last_updated FROM bandit_stats WHERE ($1::text IS NULL OR regime=$1) ORDER BY regime,template_id",regime); return {"statistics":[{**dict(r),"last_updated":int(r["last_updated"])} for r in rows]}
@app.get("/learning/feature-importance")
async def importance(model_version_id:str|None=None):
    rows=await service.db.fetch("SELECT f.model_version_id,f.feature_name,f.importance_score,m.version FROM feature_importance f JOIN model_versions m ON m.id=f.model_version_id WHERE ($1::uuid IS NULL OR f.model_version_id=$1::uuid) ORDER BY m.training_date DESC,f.importance_score DESC",model_version_id); return {"features":[{**dict(r),"model_version_id":str(r["model_version_id"])} for r in rows]}

