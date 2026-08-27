from __future__ import annotations
import asyncio,json,logging
from .engines import AnalysisPipeline
from .infrastructure import Infrastructure,resilient_loop
from .models import *
from .algorithm import AlgorithmEngine

log=logging.getLogger(__name__)
class SMCService:
    def __init__(self,infra:Infrastructure,lookback:int=5):self.infra=infra;self.pipeline=AnalysisPipeline(lookback);self.algorithm=AlgorithmEngine();self.signals={};self.task=None
    async def start(self):
        await self.restore()
        self.task=asyncio.create_task(resilient_loop(self.subscribe))
    async def stop(self):
        if self.task:self.task.cancel()
    async def restore(self):
        rows=await self.infra.db.fetch("""
          SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                 open::float8,high::float8,low::float8,close::float8,volume::float8,
                 quote_volume::float8,trades_count,is_closed
          FROM (SELECT *,row_number() OVER(PARTITION BY symbol,timeframe ORDER BY ts DESC) AS rn FROM candles) recent
          WHERE rn<=500 ORDER BY symbol,timeframe,ts
        """)
        for row in rows:self.pipeline.process(Candle.model_validate(dict(row)))
        rows=await self.infra.db.fetch("SELECT data FROM algorithm_signals WHERE status='ACTIVE'")
        for row in rows:
            item=AlgorithmSignal.model_validate_json(row["data"] if isinstance(row["data"],str) else json.dumps(row["data"]))
            self.signals[item.id]=item;self.algorithm.emitted.add(f"{item.config_id}:{item.zone_id}")
    async def subscribe(self):
        pubsub=self.infra.redis.pubsub();await pubsub.subscribe("candle.update")
        try:
            async for message in pubsub.listen():
                if message["type"]!="message":continue
                try:
                    envelope=json.loads(message["data"]);payload=envelope.get("payload",envelope)
                    if payload.get("is_closed",True):
                        await self.process(Candle.model_validate(payload),envelope.get("correlation_id"))
                except Exception:
                    log.exception("Failed to process candle event")
        finally:await pubsub.aclose()
    async def rebuild(self,symbol:str,timeframes:list[Timeframe],limit:int=500):
        symbol=symbol.strip().upper();keys=[(symbol,timeframe) for timeframe in timeframes]
        for collection in (
            self.pipeline.candles,self.pipeline.swings,self.pipeline.changes,self.pipeline.seen,
            self.pipeline.obs,self.pipeline.fvgs,self.pipeline.liquidity,
        ):
            for key in keys:collection.pop(key,None)
        for key in keys:self.pipeline.trends.pop(key,None)
        rows=await self.infra.db.fetch("""
          SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                 open::float8,high::float8,low::float8,close::float8,volume::float8,
                 quote_volume::float8,trades_count,is_closed
          FROM (SELECT *,row_number() OVER(PARTITION BY symbol,timeframe ORDER BY ts DESC) AS rn
                FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[])) recent
          WHERE rn<=$3 ORDER BY ts,timeframe
        """,symbol,[str(item) for item in timeframes],limit)
        before=len(self.signals)
        for row in rows:await self.process(Candle.model_validate(dict(row)),"history-rebuild")
        return {"symbol":symbol,"candles":len(rows),"signals_created":len(self.signals)-before}
    async def process(self,candle:Candle,correlation_id:str|None=None):
        result=self.pipeline.process(candle);key=(candle.symbol,candle.timeframe)
        mappings=[(result.swings,"swing","structure.update","swing.detected"),(result.changes,"structure_change","smc.update","structure.changed")]
        for objects,kind,topic,event in mappings:
            for item in objects:await self.infra.save(kind,item);await self.infra.publish(topic,event,item,correlation_id)
        if result.trend:await self.infra.publish("structure.update","trend.updated",result.trend,correlation_id)
        for item in result.order_blocks:
            event="orderblock.broken" if item.is_broken else "orderblock.retested" if item.retest_count else "orderblock.created"
            await self.infra.save("order_block",item);await self.infra.publish("smc.update",event,item,correlation_id)
        for item in result.fvgs:
            await self.infra.save("fvg",item);await self.infra.publish("smc.update","fvg.filled" if item.fill_percent else "fvg.created",item,correlation_id)
        for item in result.liquidity_zones:
            await self.infra.save("liquidity",item);await self.infra.publish("smc.update","liquidity.swept" if item.swept else "liquidity.detected",item,correlation_id)
        await self.infra.cache("swings",candle.symbol,candle.timeframe,self.pipeline.swings[key])
        await self.infra.cache("ob",candle.symbol,candle.timeframe,[x for x in self.pipeline.obs[key] if not x.is_broken])
        await self.infra.cache("fvg",candle.symbol,candle.timeframe,[x for x in self.pipeline.fvgs[key] if not x.is_filled])
        await self.infra.cache("liquidity",candle.symbol,candle.timeframe,[x for x in self.pipeline.liquidity[key] if not x.swept])
        generated=self.algorithm.generate(candle,self.pipeline)
        for signal in generated:
            self.signals[signal.id]=signal
            await self.infra.db.execute("INSERT INTO algorithm_signals(id,symbol,status,data,created_at) VALUES($1::uuid,$2,'ACTIVE',$3::jsonb,to_timestamp($4/1000.0)) ON CONFLICT(id) DO NOTHING",signal.id,signal.symbol,json.dumps(signal.model_dump(mode="json")),signal.created_at)
            await self.infra.publish("signal.update","algorithm.signal",signal,correlation_id)
        return result
