from __future__ import annotations
import asyncio,json,logging
from time import time
from uuid import uuid4
import asyncpg
from redis.asyncio import Redis
from .models import *
from .risk import RiskManager

log=logging.getLogger(__name__)
class DecisionService:
    """Deterministic risk/dispatch layer; no pattern selection or ML."""
    def __init__(self,database_url,redis_url,threshold=.6,min_delta=.1,default_capital=10000,**_):
        self.database_url=database_url;self.redis_url=redis_url;self.default_capital=default_capital
        self.db=None;self.redis=None;self.risk=RiskManager();self.signals={};self.tasks=[]
    async def start(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS trade_signals(id uuid PRIMARY KEY,source_signal_id uuid NOT NULL,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS risk_decisions(id bigserial PRIMARY KEY,signal_id uuid NOT NULL,approved boolean NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
        """)
        await self.db.execute("ALTER TABLE trade_signals ADD COLUMN IF NOT EXISTS source_signal_id uuid")
        await self.db.execute("""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='trade_signals' AND column_name='scenario_id')
          THEN ALTER TABLE trade_signals ALTER COLUMN scenario_id DROP NOT NULL; END IF;
        END $$""")
        self.tasks=[asyncio.create_task(self.listen())]
    async def stop(self):
        for task in self.tasks:task.cancel()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def envelope(self,event_type,payload):
        return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"decision-service","version":"2.0.0","event_type":event_type,"payload":payload.model_dump(mode="json") if isinstance(payload,BaseModel) else payload}
    async def pub(self,topic,event_type,payload):await self.redis.publish(topic,json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
    async def stream(self,topic,event_type,payload):await self.redis.xadd(topic,{"data":json.dumps(await self.envelope(event_type,payload),separators=(",",":"))},maxlen=100000,approximate=True)
    async def listen(self):
        while True:
            pubsub=self.redis.pubsub();await pubsub.subscribe("signal.update")
            try:
                async for message in pubsub.listen():
                    if message["type"]!="message":continue
                    event=json.loads(message["data"])
                    if event.get("event_type")=="algorithm.signal":await self.evaluate(AlgorithmSignal.model_validate(event["payload"]))
            except asyncio.CancelledError:await pubsub.aclose();raise
            except Exception:log.exception("Algorithm signal listener failed");await pubsub.aclose();await asyncio.sleep(2)
    async def evaluate(self,source:AlgorithmSignal):
        if source.expires_at<=int(time()*1000):return None
        signal=TradeSignal(source_signal_id=source.id,symbol=source.symbol,direction=source.direction,
          entry_price=(source.entry_zone_low+source.entry_zone_high)/2,stop_loss_price=source.stop_loss_price,
          take_profit_prices=source.take_profit_prices,target_allocations=source.target_allocations,
          break_even_rule=source.break_even_rule,move_stop_to_break_even_after_target=source.move_stop_to_break_even_after_target,
          one_trade_per_zone=source.one_trade_per_zone,deduplication_key=f"{source.config_id}:{source.zone_id}",
          quality_score=source.score,config_id=source.config_id)
        self.signals[signal.signal_id]=signal
        await self.db.execute("INSERT INTO trade_signals(id,source_signal_id,symbol,status,data,created_at) VALUES($1::uuid,$2::uuid,$3,'PENDING',$4::jsonb,to_timestamp($5/1000.0)) ON CONFLICT(id) DO NOTHING",signal.signal_id,signal.source_signal_id,signal.symbol,json.dumps(signal.model_dump(mode="json")),signal.created_at)
        await self.stream("trading.command","signal.created",signal);await self.assess(signal);return signal
    async def config(self):
        raw=await self.redis.get("risk:config");return RiskConfig.model_validate_json(raw) if raw else RiskConfig()
    async def update_config(self,patch:RiskConfigPatch):
        cfg=(await self.config()).model_copy(update=patch.model_dump(exclude_none=True));await self.redis.set("risk:config",cfg.model_dump_json());await self.pub("system.control","config.updated",{"section":"risk","config":cfg.model_dump()});return cfg
    async def assess(self,signal:TradeSignal,capital:float|None=None):
        cfg=await self.config();capital=capital or float(await self.redis.get("portfolio:equity") or self.default_capital)
        daily=float(await self.redis.get("portfolio:daily_pnl") or 0);positions=int(await self.redis.scard("positions:open"));active_orders=await self.db.fetchval("SELECT count(*) FROM orders WHERE status IN ('PENDING','OPEN')")
        recent=await self.db.fetch("SELECT pnl::float8,extract(epoch from closed_at)*1000 AS closed_at_ms FROM closed_trades ORDER BY closed_at DESC LIMIT 100")
        consecutive_losses=0;last_loss_at=None
        for row in recent:
            if row["pnl"]>=0:break
            consecutive_losses+=1
            if last_loss_at is None:last_loss_at=int(row["closed_at_ms"])
        decision=self.risk.calculate(signal,capital,cfg,daily,positions,int(active_orders or 0),consecutive_losses,last_loss_at)
        await self.db.execute("INSERT INTO risk_decisions(signal_id,approved,data) VALUES($1::uuid,$2,$3::jsonb)",signal.signal_id,decision.approved,json.dumps(decision.model_dump(mode="json")))
        if decision.approved:
            payload=decision.model_dump();payload["approved_at"]=payload.pop("timestamp");payload.pop("approved");payload.pop("rejection_reason");await self.stream("trading.command","risk.approved",payload)
        else:await self.stream("trading.command","risk.rejected",{"signal_id":signal.signal_id,"rejection_reason":decision.rejection_reason,"calculated_size":decision.position_size,"min_size":cfg.min_position_size,"timestamp":decision.timestamp})
        return decision
