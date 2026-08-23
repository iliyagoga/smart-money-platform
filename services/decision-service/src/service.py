from __future__ import annotations
import asyncio,json,logging
from time import time
from uuid import uuid4
import asyncpg
import boto3
from redis.asyncio import Redis
from .models import *
from .probability import ProbabilityEngine
from .resolver import ConflictResolver
from .risk import RiskManager
from .adaptive import AdaptiveModel

log=logging.getLogger(__name__)
class DecisionService:
    def __init__(self,database_url,redis_url,threshold=.6,min_delta=.1,default_capital=10000,minio_endpoint="http://minio:9000",minio_access_key="minioadmin",minio_secret_key="minioadmin",model_bucket="models",adaptive_weight=.35):
        self.database_url=database_url;self.redis_url=redis_url;self.default_capital=default_capital
        self.db=None;self.redis=None;self.adaptive=AdaptiveModel(adaptive_weight);self.probability=ProbabilityEngine(self.adaptive);self.resolver=ConflictResolver(threshold,min_delta);self.risk=RiskManager();self.model_bucket=model_bucket
        self.s3=boto3.client("s3",endpoint_url=minio_endpoint,aws_access_key_id=minio_access_key,aws_secret_access_key=minio_secret_key)
        self.scenarios:dict[str,Scenario]={};self.signals:dict[str,TradeSignal]={};self.tasks=[];self.pending:dict[str,asyncio.Task]={}
    async def start(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS trade_signals(id uuid PRIMARY KEY,scenario_id uuid NOT NULL,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS risk_decisions(id bigserial PRIMARY KEY,signal_id uuid NOT NULL,approved boolean NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS decision_log(id bigserial PRIMARY KEY,scenario_id uuid NOT NULL,decision text NOT NULL,reason text,created_at timestamptz NOT NULL DEFAULT now());
        """)
        rows=await self.db.fetch("SELECT data FROM scenarios WHERE status='ACTIVE'")
        for row in rows:
            try:
                s=Scenario.model_validate(row["data"]);self.scenarios[s.id]=s
            except Exception:pass
        await self.load_active_model()
        self.tasks=[asyncio.create_task(self.listen())]
    async def stop(self):
        for task in self.tasks:task.cancel()
        for task in self.pending.values():task.cancel()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def envelope(self,event_type,payload):
        return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"decision-service","version":"1.0.0","event_type":event_type,"payload":payload.model_dump(mode="json") if isinstance(payload,BaseModel) else payload}
    async def pub(self,topic,event_type,payload):await self.redis.publish(topic,json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
    async def stream(self,topic,event_type,payload):await self.redis.xadd(topic,{"data":json.dumps(await self.envelope(event_type,payload),separators=(",",":"))},maxlen=100000,approximate=True)
    async def listen(self):
        while True:
            pubsub=self.redis.pubsub();await pubsub.subscribe("scenario.update","system.state")
            try:
                async for message in pubsub.listen():
                    if message["type"]!="message":continue
                    event=json.loads(message["data"])
                    if event.get("source")=="decision-service":continue
                    if event.get("event_type")=="model.updated":await self.load_model(event["payload"]);continue
                    if event.get("event_type") in {"scenario.created","scenario.updated"}:await self.evaluate(Scenario.model_validate(event["payload"]))
            except asyncio.CancelledError:await pubsub.aclose();raise
            except Exception:log.exception("Scenario listener failed");await pubsub.aclose();await asyncio.sleep(2)
    async def evaluate(self,scenario:Scenario):
        preference=await self.bandit_preference(scenario);score=self.probability.calculate(self.probability.scenario_features(scenario),scenario,preference);scenario.confidence=score.confidence
        self.scenarios[scenario.id]=scenario
        payload={"scenario_id":scenario.id,"confidence":score.confidence,"confidence_details":score.confidence_details.model_dump()}
        await self.pub("scenario.update","scenario.confidence_updated",payload)
        old=self.pending.get(scenario.symbol)
        if old:old.cancel()
        self.pending[scenario.symbol]=asyncio.create_task(self.resolve_after_delay(scenario.symbol))
        return score
    async def bandit_preference(self,scenario):
        regime=await self.redis.get(f"regime:{scenario.symbol}:{scenario.timeframe}") or "UNKNOWN";value=await self.redis.hget(f"bandit:{regime}",scenario.setup_type);return float(value) if value is not None else None
    async def load_active_model(self):
        try:row=await self.db.fetchrow("SELECT version,path FROM model_versions WHERE is_active=true ORDER BY training_date DESC LIMIT 1")
        except asyncpg.UndefinedTableError:return
        if row:await self.load_model(dict(row))
    async def load_model(self,payload):
        path=payload.get("path","");prefix=f"s3://{self.model_bucket}/"
        if not path.startswith(prefix):raise ValueError("Unexpected model path")
        obj=await asyncio.to_thread(self.s3.get_object,Bucket=self.model_bucket,Key=path[len(prefix):]);artifact=json.loads(await asyncio.to_thread(obj["Body"].read));self.adaptive.load(artifact)
    async def resolve_after_delay(self,symbol):
        await asyncio.sleep(.15);await self.resolve(symbol)
    async def resolve(self,symbol):
        candidates=[x for x in self.scenarios.values() if x.symbol==symbol];selected,rejected=self.resolver.select(candidates)
        for scenario_id,reason in rejected.items():
            item=self.scenarios[scenario_id]
            if item.status!="ACTIVE":continue
            item.status="REJECTED";await self.db.execute("INSERT INTO decision_log(scenario_id,decision,reason) VALUES($1::uuid,'REJECTED',$2)",item.id,reason)
            await self.pub("scenario.update","scenario.rejected",{"scenario_id":item.id,"reason":reason,"rejected_at":int(time()*1000)})
        if not selected:return None
        selected.status="SELECTED";signal=self.resolver.signal(selected);self.signals[signal.signal_id]=signal
        await self.db.execute("INSERT INTO decision_log(scenario_id,decision) VALUES($1::uuid,'SELECTED')",selected.id)
        await self.db.execute("INSERT INTO trade_signals(id,scenario_id,symbol,status,data,created_at) VALUES($1::uuid,$2::uuid,$3,'PENDING',$4::jsonb,to_timestamp($5/1000.0)) ON CONFLICT(id) DO NOTHING",signal.signal_id,signal.scenario_id,signal.symbol,json.dumps(signal.model_dump(mode="json")),signal.created_at)
        await self.pub("scenario.update","scenario.selected",{"scenario_id":selected.id,"confidence":selected.confidence,"selected_at":int(time()*1000)})
        await self.stream("trading.command","signal.created",signal)
        await self.assess(signal)
        return signal
    async def config(self):
        raw=await self.redis.get("risk:config");return RiskConfig.model_validate_json(raw) if raw else RiskConfig()
    async def update_config(self,patch:RiskConfigPatch):
        cfg=(await self.config()).model_copy(update=patch.model_dump(exclude_none=True));await self.redis.set("risk:config",cfg.model_dump_json());await self.pub("system.control","config.updated",{"section":"risk","config":cfg.model_dump()});return cfg
    async def assess(self,signal:TradeSignal,capital:float|None=None):
        cfg=await self.config();capital=capital or float(await self.redis.get("portfolio:equity") or self.default_capital)
        daily=float(await self.redis.get("portfolio:daily_pnl") or 0);positions=int(await self.redis.scard("positions:open"))
        decision=self.risk.calculate(signal,capital,cfg,daily,positions)
        await self.db.execute("INSERT INTO risk_decisions(signal_id,approved,data) VALUES($1::uuid,$2,$3::jsonb)",signal.signal_id,decision.approved,json.dumps(decision.model_dump(mode="json")))
        if decision.approved:
            payload=decision.model_dump();payload["approved_at"]=payload.pop("timestamp");payload.pop("approved");payload.pop("rejection_reason")
            await self.stream("trading.command","risk.approved",payload)
        else:
            await self.stream("trading.command","risk.rejected",{"signal_id":signal.signal_id,"rejection_reason":decision.rejection_reason,"calculated_size":decision.position_size,"min_size":cfg.min_position_size,"timestamp":decision.timestamp})
        return decision
