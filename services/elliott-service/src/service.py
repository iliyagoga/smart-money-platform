from __future__ import annotations
import asyncio,json,logging
import asyncpg
from collections import defaultdict
from .infrastructure import Infrastructure,resilient_loop
from .models import *
from .elliott_live import ElliottLiveEngine, normalize_config

log=logging.getLogger(__name__)
class ElliottService:
    def __init__(self,infra:Infrastructure):
        self.infra=infra;self.candles=defaultdict(list);self.scenarios={};self.elliott=ElliottLiveEngine();self.task=None
    def store_candle(self,candle:Candle):
        bars=self.candles[(candle.symbol,candle.timeframe)]
        bars[:]=[item for item in bars if item.timestamp!=candle.timestamp]
        bars.append(candle);bars.sort(key=lambda item:item.timestamp);del bars[:-500]
    async def start(self):
        await self.restore()
        await self.restore_elliott_patterns()
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
        for row in rows:self.store_candle(Candle.model_validate(dict(row)))
        scenarios=await self.infra.db.fetch("SELECT data FROM scenarios WHERE status='ACTIVE' AND data->>'setup_type'='ELLIOTT_WAVE3'")
        for row in scenarios:
            item=Scenario.model_validate_json(row["data"] if isinstance(row["data"],str) else json.dumps(row["data"]))
            self.scenarios[item.id]=item
        live_elliott=await self.infra.db.fetch("SELECT data FROM scenarios WHERE data->>'setup_type'='ELLIOTT_WAVE3'")
        for row in live_elliott:
            value=json.loads(row["data"]) if isinstance(row["data"],str) else row["data"]
            pattern_id=value.get("id")
            if pattern_id:
                self.elliott.emitted.add(pattern_id)
                self.elliott.live_signal_ids.add(pattern_id)
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
        for key in keys:self.candles.pop(key,None)
        rows=await self.infra.db.fetch("""
          SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                 open::float8,high::float8,low::float8,close::float8,volume::float8,
                 quote_volume::float8,trades_count,is_closed
          FROM (SELECT *,row_number() OVER(PARTITION BY symbol,timeframe ORDER BY ts DESC) AS rn
                FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[])) recent
          WHERE rn<=$3 ORDER BY ts,timeframe
        """,symbol,[str(item) for item in timeframes],limit)
        before=len(self.scenarios)
        for row in rows:await self.process(Candle.model_validate(dict(row)),"history-rebuild")
        return {"symbol":symbol,"candles":len(rows),"scenarios_created":len(self.scenarios)-before}
    async def trading_config(self,symbol:str):
        try:
            row=await self.infra.db.fetchrow(
                """SELECT tc.config,ta.tick_size,ta.lot_size,ta.minimum_order_size,
                  ta.maker_fee_rate,ta.taker_fee_rate,ta.funding_rate
                  FROM trading_configs tc JOIN trading_assets ta ON ta.symbol=tc.symbol
                  WHERE tc.symbol=$1 AND tc.status='ACTIVE' AND ta.validation_status='ACTIVE'""",symbol,
            )
        except asyncpg.UndefinedTableError:
            return None
        if not row:return None
        value=row["config"];value=json.loads(value) if isinstance(value,str) else dict(value)
        value={**value,"tickSize":row["tick_size"],"lotSize":row["lot_size"],
          "minimumOrderSize":row["minimum_order_size"],"makerFeePercent":abs(row["maker_fee_rate"] or 0)*100,
          "takerFeePercent":abs(row["taker_fee_rate"] or 0)*100,"fundingPercentPerDay":(row["funding_rate"] or 0)*300}
        return value
    async def restore_elliott_patterns(self):
        try:rows=await self.infra.db.fetch("SELECT symbol,config FROM trading_configs WHERE status='ACTIVE'")
        except asyncpg.UndefinedTableError:return
        for row in rows:
            raw=json.loads(row["config"]) if isinstance(row["config"],str) else row["config"]
            normalized=normalize_config(raw)
            if normalized.get("strategy")!="ELLIOTT":continue
            try:
                timeframe=Timeframe(normalized.get("elliott",{}).get("entry_timeframe","M15"))
                candles=self.candles.get((row["symbol"],timeframe),[])
                if candles:self.elliott.generate(row["symbol"],candles[-1],self.candles,raw,allow_live_emit=False)
            except (ValueError,KeyError):log.exception("Could not restore Elliott waves for %s",row["symbol"])
    async def process(self,candle:Candle,correlation_id:str|None=None):
        self.store_candle(candle)
        trading_config=await self.trading_config(candle.symbol)
        strategy=(normalize_config(trading_config or {}).get("strategy") if trading_config else None)
        if strategy=="ELLIOTT":
            try:generated=self.elliott.generate(candle.symbol,candle,self.candles,trading_config,
                                                allow_live_emit=correlation_id != "history-rebuild")
            except (ValueError,KeyError):
                log.exception("Invalid Elliott live config for %s",candle.symbol);generated=[]
        else:generated=[]
        for scenario in generated:
            self.scenarios[scenario.id]=scenario
            await self.infra.db.execute("INSERT INTO scenarios(id,symbol,status,data,created_at) VALUES($1::uuid,$2,$3,$4::jsonb,to_timestamp($5/1000.0)) ON CONFLICT(id) DO NOTHING",scenario.id,scenario.symbol,scenario.status,json.dumps(scenario.model_dump(mode="json")),scenario.created_at)
            await self.infra.publish("scenario.update","scenario.created",scenario,correlation_id)
        return {"symbol":candle.symbol,"timeframe":candle.timeframe,"scenarios_created":len(generated)}
