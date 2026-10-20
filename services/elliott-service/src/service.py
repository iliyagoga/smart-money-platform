from __future__ import annotations
import asyncio,hashlib,json,logging
import asyncpg
from collections import defaultdict
from .infrastructure import Infrastructure,resilient_loop
from .models import *
from .elliott_live import ElliottLiveEngine, normalize_config
from .okx_market import OkxMarketDataUnavailable,OkxMarketSource,TIMEFRAME_MILLISECONDS

log=logging.getLogger(__name__)
class ElliottService:
    def __init__(self,infra:Infrastructure,okx_rest_url:str|None=None):
        self.infra=infra;self.candles=defaultdict(list);self.scenarios={};self.elliott=ElliottLiveEngine();self.task=None
        self.history_tasks:dict[str,asyncio.Task]={};self.outbox_task=None
        self.live_market=OkxMarketSource(okx_rest_url) if okx_rest_url else None
    def store_candle(self,candle:Candle):
        bars=self.candles[(candle.symbol,candle.timeframe)]
        bars[:]=[item for item in bars if item.timestamp!=candle.timestamp]
        bars.append(candle);bars.sort(key=lambda item:item.timestamp);del bars[:-500]
    async def start(self):
        await self.restore()
        await self.restore_elliott_patterns()
        self.task=asyncio.create_task(resilient_loop(self.subscribe))
        await self.publish_pending_scenarios()
        self.outbox_task=asyncio.create_task(resilient_loop(self.outbox_loop))
        try:rows=await self.infra.db.fetch("SELECT symbol FROM trading_configs WHERE status='ACTIVE'")
        except asyncpg.UndefinedTableError:rows=[]
        for row in rows:self.schedule_history_snapshot(row["symbol"])
    async def stop(self):
        if self.task:self.task.cancel()
        if self.outbox_task:self.outbox_task.cancel()
        for task in self.history_tasks.values():task.cancel()
        if self.live_market:await self.live_market.close()

    async def outbox_loop(self):
        while True:
            await self.publish_pending_scenarios()
            await asyncio.sleep(2)

    async def publish_pending_scenarios(self,scenario_id:str|None=None):
        rows=await self.infra.db.fetch("""SELECT s.data,o.correlation_id FROM elliott_scenario_outbox o
          JOIN scenarios s ON s.id=o.scenario_id WHERE o.published_at IS NULL
          AND ($1::uuid IS NULL OR o.scenario_id=$1::uuid) ORDER BY o.created_at LIMIT 100""",scenario_id)
        for row in rows:
            scenario=Scenario.model_validate_json(row["data"] if isinstance(row["data"],str) else json.dumps(row["data"]))
            await self.infra.publish("scenario.update","scenario.created",scenario,row["correlation_id"])
            await self.infra.db.execute("UPDATE elliott_scenario_outbox SET published_at=now() WHERE scenario_id=$1::uuid",scenario.id)
            self.scenarios[scenario.id]=scenario;self.elliott.emitted.add(scenario.id);self.elliott.live_signal_ids.add(scenario.id)
            for item in self.elliott.latest_entries.get(scenario.symbol,[]):
                if item["id"]==scenario.id:item["origin"]="LIVE";break
    async def restore(self):
        rows=await self.infra.db.fetch("""
          SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                 open::float8,high::float8,low::float8,close::float8,volume::float8,
                 quote_volume::float8,trades_count,is_closed
          FROM (SELECT *,row_number() OVER(PARTITION BY symbol,timeframe ORDER BY ts DESC) AS rn FROM candles
                WHERE is_closed) recent
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
        pubsub=self.infra.redis.pubsub();await pubsub.subscribe("candle.update","trading.config")
        try:
            async for message in pubsub.listen():
                if message["type"]!="message":continue
                try:
                    envelope=json.loads(message["data"]);payload=envelope.get("payload",envelope)
                    if message["channel"]=="trading.config":
                        symbol=str(payload.get("symbol","")).strip().upper()
                        if symbol and envelope.get("event_type")=="trading.config.saved":self.schedule_history_snapshot(symbol)
                    elif payload.get("is_closed",True):
                        await self.process(Candle.model_validate(payload),envelope.get("correlation_id"))
                except Exception:
                    log.exception("Failed to process Elliott event")
        finally:await pubsub.aclose()
    async def rebuild(self,symbol:str,timeframes:list[Timeframe],limit:int=500):
        symbol=symbol.strip().upper();keys=[(symbol,timeframe) for timeframe in timeframes]
        for key in keys:self.candles.pop(key,None)
        rows=await self.infra.db.fetch("""
          SELECT symbol,timeframe,(extract(epoch FROM ts)*1000)::bigint AS timestamp,
                 open::float8,high::float8,low::float8,close::float8,volume::float8,
                 quote_volume::float8,trades_count,is_closed
          FROM (SELECT *,row_number() OVER(PARTITION BY symbol,timeframe ORDER BY ts DESC) AS rn
                FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[]) AND is_closed) recent
          WHERE rn<=$3 ORDER BY ts,timeframe
        """,symbol,[str(item) for item in timeframes],limit)
        before=len(self.scenarios)
        for row in rows:await self.process(Candle.model_validate(dict(row)),"history-rebuild")
        await self.rebuild_history_snapshot(symbol)
        return {"symbol":symbol,"candles":len(rows),"scenarios_created":len(self.scenarios)-before}

    def schedule_history_snapshot(self,symbol:str):
        symbol=symbol.strip().upper()
        previous=self.history_tasks.get(symbol)
        if previous and not previous.done():previous.cancel()
        task=asyncio.create_task(self.rebuild_history_snapshot(symbol))
        self.history_tasks[symbol]=task
        task.add_done_callback(lambda completed:self.history_tasks.pop(symbol,None)
                               if self.history_tasks.get(symbol) is completed else None)

    async def history_snapshot(self,symbol:str):
        symbol=symbol.strip().upper()
        row=await self.infra.db.fetchrow(
            "SELECT status,data,error,(extract(epoch FROM updated_at)*1000)::bigint updated_at FROM elliott_history_snapshots WHERE symbol=$1",
            symbol,
        )
        if not row:return {"symbol":symbol,"status":"NOT_BUILT","patterns":[],"entries":[],"orders":[],"trades":[]}
        data=json.loads(row["data"]) if isinstance(row["data"],str) else dict(row["data"])
        return {"symbol":symbol,"status":row["status"],"error":row["error"],"updated_at":row["updated_at"],
                "patterns":[],"entries":[],"orders":[],"trades":[],**data}

    async def rebuild_history_snapshot(self,symbol:str):
        """Build an isolated paper replay. It never writes to orders, positions or closed_trades."""
        from backtest_core.elliott import run_elliott_replay
        from backtest_core.models import BacktestConfig

        symbol=symbol.strip().upper();raw=await self.trading_config(symbol)
        if not raw:return None
        normalized=normalize_config(raw);config=BacktestConfig.model_validate(normalized)
        config_hash=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
        progress_data={"progress":0,"phase":"Подготовка данных"}
        await self.infra.db.execute("""INSERT INTO elliott_history_snapshots(symbol,status,config_hash,data,error)
          VALUES($1,'BUILDING',$2,$3::jsonb,NULL) ON CONFLICT(symbol) DO UPDATE SET
          status='BUILDING',config_hash=excluded.config_hash,data=excluded.data,error=NULL,updated_at=now()""",
          symbol,config_hash,json.dumps(progress_data))
        await self._publish_history_progress(symbol,"BUILDING",progress_data)
        try:
            duration={"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240,"D1":1440}
            ec=config.elliott;required=list(dict.fromkeys((ec.entry_timeframe,ec.structure_timeframe,ec.macro_timeframe)))
            macro_minutes=duration[ec.macro_timeframe]
            candles_by_tf={}
            for index,timeframe in enumerate(required):
                limit=min(200_000,max(500,(500*macro_minutes+duration[timeframe]-1)//duration[timeframe]))
                rows=await self.infra.db.fetch("""SELECT symbol,timeframe,
                  (extract(epoch FROM ts)*1000)::bigint AS timestamp,open::float8,high::float8,
                  low::float8,close::float8,volume::float8,quote_volume::float8,trades_count,is_closed
                  FROM (SELECT * FROM candles WHERE symbol=$1 AND timeframe=$2 AND is_closed
                        ORDER BY ts DESC LIMIT $3) history ORDER BY ts""",symbol,timeframe,limit)
                candles_by_tf[timeframe]=[dict(row) for row in rows]
                await self._update_history_progress(symbol,config_hash,5+int((index+1)/len(required)*15),f"Подготовка {timeframe}")
            missing=[timeframe for timeframe,items in candles_by_tf.items() if not items]
            if missing:
                data={"patterns":[],"entries":[],"orders":[],"trades":[],"summary":{},
                      "message":f"Waiting for candles: {', '.join(missing)}"}
                await self._save_history_snapshot(symbol,"WAITING_FOR_DATA",config_hash,data)
                return data
            loop=asyncio.get_running_loop();reported=-1
            def replay_progress(progress:int,phase:str):
                nonlocal reported
                overall=20+int(progress*.78)
                if overall<=reported:return
                reported=overall
                asyncio.run_coroutine_threadsafe(
                    self._update_history_progress(symbol,config_hash,overall,phase),loop,
                ).result(timeout=10)
            result=await asyncio.to_thread(run_elliott_replay,candles_by_tf,config,None,replay_progress)
            patterns=result.get("elliott_patterns",[])
            trades=[{**trade,"id":f"history-{symbol}-{trade.get('pattern_id')}-{trade.get('entry_time')}",
                     "symbol":symbol,"origin":"HISTORICAL_PAPER"} for trade in result.get("trades",[])]
            entry_type=("LIMIT" if str(ec.entry_model) in {"CHOCH_RETRACE","WAVE1_BREAK_RETRACE","DISPLACEMENT_RETRACE"}
                        else "STOP" if str(ec.entry_model) in {"WAVE1_BREAK_STOP","P2_LIQUIDITY_SWEEP","VOLUME_EXPANSION"}
                        else "MARKET")
            entries=[{"id":trade["id"],"direction":trade["direction"],"setup_type":"ELLIOTT_WAVE3",
                      "status":"FILLED","entry_type":entry_type,"entry_zone_low":trade["entry_price"],
                      "entry_zone_high":trade["entry_price"],"created_at":trade["entry_time"],
                      "expires_at":trade["entry_time"]+duration[ec.entry_timeframe]*60_000,
                      "entry_model":str(ec.entry_model),"origin":"HISTORICAL",
                      "stop_loss_price":trade.get("initial_stop"),
                      "take_profit_prices":trade.get("take_profit_prices",[]),"trade_id":trade["id"]}
                     for trade in trades]
            orders=[{"id":entry["id"],"symbol":symbol,"side":"BUY" if entry["direction"]=="LONG" else "SELL",
                     "type":entry["entry_type"],"status":"FILLED","price":entry["entry_zone_low"],
                     "quantity":trade.get("quantity",0),"stop_loss_price":entry.get("stop_loss_price"),
                     "take_profit_prices":entry.get("take_profit_prices",[]),"filled_at":entry["created_at"],
                     "origin":"HISTORICAL_PAPER","trade_id":entry["trade_id"]}
                    for entry,trade in zip(entries,trades)]
            data={"patterns":patterns,"entries":entries,"orders":orders,"trades":trades,
                  "summary":{"total_trades":result.get("total_trades",0),"net_pnl":result.get("net_profit",0),
                             "win_rate":result.get("win_rate",0),"initial_capital":result.get("initial_capital",0),
                             "final_capital":result.get("final_capital",0)},
                  "dataset":result.get("dataset",{})}
            await self._save_history_snapshot(symbol,"COMPLETED",config_hash,data)
            return data
        except asyncio.CancelledError:raise
        except Exception as exc:
            log.exception("Could not build historical paper replay for %s",symbol)
            await self.infra.db.execute("UPDATE elliott_history_snapshots SET status='FAILED',error=$2,updated_at=now() WHERE symbol=$1",symbol,str(exc)[:2000])
            await self._publish_history_progress(symbol,"FAILED",{"progress":reported if 'reported' in locals() else 0,"phase":"Ошибка расчёта","error":str(exc)[:2000]})
            return None

    async def _save_history_snapshot(self,symbol,status,config_hash,data):
        await self.infra.db.execute("""UPDATE elliott_history_snapshots SET status=$2,config_hash=$3,
          data=$4::jsonb,error=NULL,updated_at=now() WHERE symbol=$1""",symbol,status,config_hash,json.dumps(data,separators=(",",":"),default=str))
        await self._publish_history_progress(symbol,status,data)
    async def _update_history_progress(self,symbol,config_hash,progress,phase):
        data={"progress":progress,"phase":phase}
        updated=await self.infra.db.execute("""UPDATE elliott_history_snapshots SET
          data=data || $3::jsonb,updated_at=now() WHERE symbol=$1 AND config_hash=$2""",symbol,config_hash,json.dumps(data))
        if updated!="UPDATE 0":await self._publish_history_progress(symbol,"BUILDING",data)
    async def _publish_history_progress(self,symbol,status,data):
        if not hasattr(self.infra,"publish"):return
        payload={"symbol":symbol,"status":status,"progress":100 if status=="COMPLETED" else data.get("progress",0),
                 "phase":data.get("phase","Расчёт завершён" if status=="COMPLETED" else ""),"error":data.get("error")}
        await self.infra.publish("history.update","history.calculation_progress",payload)
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
        normalized=normalize_config(trading_config or {})
        strategy=(normalized.get("strategy") if trading_config else None)
        if strategy=="ELLIOTT":
            try:
                candle_source=self.candles;analysis_candle=candle
                ec=normalized.get("elliott",{})
                entry_timeframe=ec.get("entry_timeframe","M15")
                if self.live_market and correlation_id != "history-rebuild" and str(candle.timeframe)==entry_timeframe:
                    macro_timeframe=ec.get("macro_timeframe","H4")
                    required=list(dict.fromkeys((entry_timeframe,ec.get("structure_timeframe","H1"),macro_timeframe)))
                    macro_duration=TIMEFRAME_MILLISECONDS[macro_timeframe]
                    limits={timeframe:min(200_000,max(500,(500*macro_duration+TIMEFRAME_MILLISECONDS[timeframe]-1)
                                                          //TIMEFRAME_MILLISECONDS[timeframe]))
                            for timeframe in required}
                    candle_source=await self.live_market.load(candle.symbol,limits,entry_timeframe,candle.timestamp)
                    analysis_candle=candle_source[(candle.symbol,Timeframe(entry_timeframe))][-1]
                generated=self.elliott.generate(candle.symbol,analysis_candle,candle_source,trading_config,
                                                allow_live_emit=correlation_id != "history-rebuild")
            except OkxMarketDataUnavailable as exc:
                log.warning("Live Elliott analysis is waiting for complete OKX data for %s: %s",candle.symbol,exc)
                generated=[]
            except (ValueError,KeyError):
                log.exception("Invalid Elliott live config for %s",candle.symbol);generated=[]
        else:generated=[]
        for scenario in generated:
            await self.infra.db.execute("""WITH inserted AS (
              INSERT INTO scenarios(id,symbol,status,data,created_at)
              VALUES($1::uuid,$2,$3,$4::jsonb,to_timestamp($5/1000.0))
              ON CONFLICT(id) DO NOTHING RETURNING id)
              INSERT INTO elliott_scenario_outbox(scenario_id,correlation_id)
              SELECT id,$6 FROM inserted ON CONFLICT(scenario_id) DO NOTHING""",
              scenario.id,scenario.symbol,scenario.status,json.dumps(scenario.model_dump(mode="json")),
              scenario.created_at,correlation_id)
            await self.publish_pending_scenarios(scenario.id)
        return {"symbol":candle.symbol,"timeframe":candle.timeframe,"scenarios_created":len(generated)}
