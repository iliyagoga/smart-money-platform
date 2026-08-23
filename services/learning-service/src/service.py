from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from time import time
from uuid import uuid4

import asyncpg
import boto3
from redis.asyncio import Redis

from .algorithms import FEATURE_NAMES, thompson_preferences, train_walk_forward


def decode(value):
    return json.loads(value) if isinstance(value, str) else value


class LearningService:
    def __init__(self, settings):
        self.settings = settings; self.db = None; self.redis = None; self.task = None
        self.s3 = boto3.client("s3", endpoint_url=settings.minio_endpoint, aws_access_key_id=settings.minio_access_key, aws_secret_access_key=settings.minio_secret_key)

    async def start(self):
        self.db = await asyncpg.create_pool(self.settings.database_url, min_size=1, max_size=5)
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True); await self.redis.ping()
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS learning_samples(id uuid PRIMARY KEY,position_id uuid UNIQUE NOT NULL,scenario_id uuid,symbol text NOT NULL,regime text NOT NULL,template_id text NOT NULL,features jsonb NOT NULL,outcome smallint NOT NULL CHECK(outcome IN(0,1)),created_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS model_versions(id uuid PRIMARY KEY,model_type text NOT NULL,version text UNIQUE NOT NULL,path text NOT NULL,metrics jsonb NOT NULL,training_samples_count integer NOT NULL,is_active boolean NOT NULL DEFAULT false,training_date timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS bandit_stats(regime text NOT NULL,template_id text NOT NULL,successes integer NOT NULL DEFAULT 0,failures integer NOT NULL DEFAULT 0,last_updated timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(regime,template_id));
          CREATE TABLE IF NOT EXISTS feature_importance(model_version_id uuid NOT NULL REFERENCES model_versions(id),feature_name text NOT NULL,importance_score double precision NOT NULL,PRIMARY KEY(model_version_id,feature_name));
        """)
        await asyncio.to_thread(self.ensure_bucket)
        await self.backfill(); self.task = asyncio.create_task(self.listen())

    async def stop(self):
        if self.task: self.task.cancel()
        if self.redis: await self.redis.aclose()
        if self.db: await self.db.close()

    def ensure_bucket(self):
        names = [item["Name"] for item in self.s3.list_buckets().get("Buckets", [])]
        if self.settings.model_bucket not in names: self.s3.create_bucket(Bucket=self.settings.model_bucket)

    async def envelope(self, event_type, payload):
        return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"learning-service","version":"1.0.0","event_type":event_type,"payload":payload}

    async def publish(self, channel, event_type, payload):
        await self.redis.publish(channel, json.dumps(await self.envelope(event_type, payload), separators=(",", ":")))

    async def backfill(self):
        rows = await self.db.fetch("SELECT data FROM closed_trades t WHERE NOT EXISTS(SELECT 1 FROM learning_samples s WHERE s.position_id=t.position_id) ORDER BY closed_at")
        for row in rows: await self.prepare(decode(row["data"]))

    async def listen(self):
        while True:
            pubsub = self.redis.pubsub(); await pubsub.subscribe("position.update")
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message": continue
                    event = json.loads(message["data"])
                    if event.get("event_type") == "position.closed": await self.prepare(event["payload"], event.get("correlation_id"))
            except asyncio.CancelledError: await pubsub.aclose(); raise
            except Exception: await pubsub.aclose(); await asyncio.sleep(2)

    async def scenario(self, scenario_id):
        if not scenario_id: return {}
        row = await self.db.fetchrow("SELECT data FROM scenarios WHERE id=$1::uuid", scenario_id)
        return decode(row["data"]) if row else {}

    async def prepare(self, trade, correlation_id=None):
        scenario = await self.scenario(trade.get("scenario_id")); entry = float(trade.get("entry_price", 0)); exit_price = float(trade.get("exit_price", entry)); pnl = float(trade.get("pnl", 0))
        stop = float(scenario.get("stop_loss_price", entry)); targets = scenario.get("take_profit_prices") or [exit_price]
        risk = abs(entry - stop); reward = abs(float(targets[0]) - entry)
        regime = scenario.get("regime", "UNKNOWN"); template = scenario.get("setup_type", "UNKNOWN")
        features = {"confidence":float(scenario.get("confidence", 0)),"risk_reward":reward/risk if risk else 0,"pnl_excursion_ratio":float(trade.get("max_unrealized_pnl",0))/max(abs(float(trade.get("max_unrealized_loss",0))),1),"duration_log":min(float(trade.get("duration_seconds",0))/86400,1),"direction_long":1 if trade.get("direction")=="LONG" else 0}
        sample_id = str(uuid4()); created = int(trade.get("closed_at", time()*1000)); outcome = 1 if pnl > 0 else 0
        inserted = await self.db.fetchval("INSERT INTO learning_samples(id,position_id,scenario_id,symbol,regime,template_id,features,outcome,created_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7::jsonb,$8,to_timestamp($9/1000.0)) ON CONFLICT(position_id) DO NOTHING RETURNING id",sample_id,trade["position_id"],trade.get("scenario_id"),trade["symbol"],regime,template,json.dumps(features),outcome,created)
        if not inserted: return None
        await self.db.execute("INSERT INTO bandit_stats(regime,template_id,successes,failures) VALUES($1,$2,$3,$4) ON CONFLICT(regime,template_id) DO UPDATE SET successes=bandit_stats.successes+excluded.successes,failures=bandit_stats.failures+excluded.failures,last_updated=now()",regime,template,outcome,1-outcome)
        await self.refresh_bandit(regime); payload={"sample_id":sample_id,"scenario_id":trade.get("scenario_id"),"symbol":trade["symbol"],"features":features,"outcome":outcome,"regime":regime,"created_at":created,"correlation_id":correlation_id}
        await self.redis.xadd("learning.update", {"data":json.dumps(await self.envelope("sample.ready",payload),separators=(",",":"))}, maxlen=100000, approximate=True)
        return payload

    async def refresh_bandit(self, regime):
        rows=await self.db.fetch("SELECT template_id,successes,failures FROM bandit_stats WHERE regime=$1",regime); stats={r["template_id"]:(r["successes"],r["failures"]) for r in rows}; preferences=thompson_preferences(stats)
        await self.redis.hset(f"bandit:{regime}",mapping={k:str(v) for k,v in preferences.items()}); await self.publish("system.state","bandit.updated",{"regime":regime,"preferences":preferences,"updated_at":int(time()*1000)})
        return preferences

    async def samples(self):
        rows=await self.db.fetch("SELECT features,outcome,created_at FROM learning_samples ORDER BY created_at")
        return [{"features":decode(r["features"]),"outcome":r["outcome"],"created_at":int(r["created_at"].timestamp()*1000)} for r in rows]

    async def train(self):
        samples=await self.samples()
        if len(samples)<self.settings.minimum_training_samples: raise ValueError(f"At least {self.settings.minimum_training_samples} samples are required; available: {len(samples)}")
        model,metrics=train_walk_forward(samples); stamp=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"); version=f"v{stamp}"; key=f"{self.settings.model_type.lower()}/{version}.json"; artifact={"model_type":self.settings.model_type,"version":version,**model}
        await asyncio.to_thread(self.s3.put_object,Bucket=self.settings.model_bucket,Key=key,Body=json.dumps(artifact).encode(),ContentType="application/json")
        model_id=str(uuid4()); await self.db.execute("UPDATE model_versions SET is_active=false WHERE model_type=$1",self.settings.model_type)
        await self.db.execute("INSERT INTO model_versions(id,model_type,version,path,metrics,training_samples_count,is_active,training_date) VALUES($1::uuid,$2,$3,$4,$5::jsonb,$6,true,now())",model_id,self.settings.model_type,version,f"s3://{self.settings.model_bucket}/{key}",json.dumps(metrics),len(samples))
        for name,weight in zip(FEATURE_NAMES,model["weights"]): await self.db.execute("INSERT INTO feature_importance(model_version_id,feature_name,importance_score) VALUES($1::uuid,$2,$3)",model_id,name,abs(weight))
        await self.redis.set(f"models:active:{self.settings.model_type}",version); payload={"model_type":self.settings.model_type,"version":version,"path":f"s3://{self.settings.model_bucket}/{key}","metrics":metrics,"training_date":int(time()*1000),"samples_count":len(samples),"is_active":True}; await self.publish("system.state","model.updated",payload); return payload
