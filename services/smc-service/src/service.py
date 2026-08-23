from __future__ import annotations
import asyncio,json,logging
from .engines import AnalysisPipeline
from .infrastructure import Infrastructure,resilient_loop
from .models import *
from .scenarios import ScenarioManager

log=logging.getLogger(__name__)
class SMCService:
    def __init__(self,infra:Infrastructure,lookback:int=5):self.infra=infra;self.pipeline=AnalysisPipeline(lookback);self.scenarios=ScenarioManager();self.task=None
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
        scenarios=await self.infra.db.fetch("SELECT data FROM scenarios WHERE status='ACTIVE'")
        for row in scenarios:
            item=Scenario.model_validate_json(row["data"] if isinstance(row["data"],str) else json.dumps(row["data"]))
            self.scenarios.items[item.id]=item
    async def subscribe(self):
        pubsub=self.infra.redis.pubsub();await pubsub.subscribe("candle.update")
        try:
            async for message in pubsub.listen():
                if message["type"]!="message":continue
                envelope=json.loads(message["data"]);payload=envelope.get("payload",envelope)
                if payload.get("is_closed",True):await self.process(Candle.model_validate(payload),envelope.get("correlation_id"))
        finally:await pubsub.aclose()
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
        generated=self.scenarios.generate(candle.symbol,candle.timeframe,self.pipeline.obs[key],self.pipeline.fvgs[key],self.pipeline.liquidity[key])
        for scenario in generated:
            await self.infra.db.execute("INSERT INTO scenarios(id,symbol,status,data,created_at) VALUES($1::uuid,$2,$3,$4::jsonb,to_timestamp($5/1000.0)) ON CONFLICT(id) DO NOTHING",scenario.id,scenario.symbol,scenario.status,json.dumps(scenario.model_dump(mode="json")),scenario.created_at)
            await self.infra.publish("scenario.update","scenario.created",scenario,correlation_id)
        return result
