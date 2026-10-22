from __future__ import annotations
import asyncio,json,logging
from datetime import datetime,timezone
from time import time
from uuid import uuid4
import asyncpg,httpx
from redis.asyncio import Redis
from .models import *
from .resolver import ConflictResolver
from .risk import RiskManager

log=logging.getLogger(__name__)
def decode_json(value):return json.loads(value) if isinstance(value,str) else value
def config_value(config:dict,camel:str,snake:str,default=None):
    return config.get(camel,config.get(snake,default))
def simulated_elliott_scenario(request:SimulatedElliottSignalRequest,entry:float,created:int):
    side=1 if request.direction=="LONG" else -1;risk=entry*request.risk_percent/100
    return Scenario(id=str(uuid4()),symbol=request.symbol,timeframe="M1",direction=request.direction,
      setup_type="ELLIOTT_WAVE3",confidence=1,entry_zone_low=entry,entry_zone_high=entry,entry_type="MARKET",
      stop_loss_price=entry-side*risk,take_profit_prices=[entry+side*risk*request.reward_r],
      target_allocations=[1.0],target_rrs=[request.reward_r],break_even_rule="OFF",
      reasons=["Simulated Elliott signal"],objects_used=[{"kind":"ELLIOTT_SIMULATION"}],
      created_at=created,expires_at=created+300_000)
class DecisionService:
    def __init__(self,database_url,redis_url,threshold=.6,min_delta=.1,default_capital=10000,
                 exchange_service_url="http://exchange-gateway:8070"):
        self.database_url=database_url;self.redis_url=redis_url;self.default_capital=default_capital
        self.exchange_service_url=exchange_service_url.rstrip("/");self.http=None
        self.db=None;self.redis=None;self.resolver=ConflictResolver(threshold,min_delta);self.risk=RiskManager()
        self.scenarios:dict[str,Scenario]={};self.signals:dict[str,TradeSignal]={};self.tasks=[];self.pending:dict[str,asyncio.Task]={}
        self.waiting:set[str]=set();self.reserved_signal_id:str|None=None
        self.risk_lock=asyncio.Lock();self.resolve_lock=asyncio.Lock()
    async def start(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        self.http=httpx.AsyncClient(timeout=10)
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS trade_signals(id uuid PRIMARY KEY,scenario_id uuid NOT NULL,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS risk_decisions(id bigserial PRIMARY KEY,signal_id uuid NOT NULL,approved boolean NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS decision_log(id bigserial PRIMARY KEY,scenario_id uuid NOT NULL,decision text NOT NULL,reason text,created_at timestamptz NOT NULL DEFAULT now());
        """)
        rows=await self.db.fetch("SELECT data FROM scenarios WHERE status='ACTIVE' AND data->>'setup_type'='ELLIOTT_WAVE3'")
        for row in rows:
            try:
                s=Scenario.model_validate(decode_json(row["data"]))
                if s.expires_at>now_ms():self.scenarios[s.id]=s
                else:await self.db.execute("UPDATE scenarios SET status='EXPIRED' WHERE id=$1::uuid",s.id)
            except Exception:log.exception("Could not restore Elliott scenario")
        rows=await self.db.fetch("SELECT data FROM trade_signals WHERE status='WAITING'")
        for row in rows:
            try:
                signal=TradeSignal.model_validate(decode_json(row["data"]))
                if signal.expires_at is None or signal.expires_at>now_ms():
                    self.signals[signal.signal_id]=signal;self.waiting.add(signal.signal_id)
            except Exception:log.exception("Could not restore waiting trade signal")
        self.tasks=[asyncio.create_task(self.listen()),asyncio.create_task(self.recover())]
        for scenario in list(self.scenarios.values()):await self.evaluate(scenario)
    async def stop(self):
        for task in self.tasks:task.cancel()
        for task in self.pending.values():task.cancel()
        if self.redis:await self.redis.aclose()
        if self.http:await self.http.aclose()
        if self.db:await self.db.close()
    async def envelope(self,event_type,payload):
        return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"decision-service","version":"1.0.0","event_type":event_type,"payload":payload.model_dump(mode="json") if isinstance(payload,BaseModel) else payload}
    async def pub(self,topic,event_type,payload):await self.redis.publish(topic,json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
    async def stream(self,topic,event_type,payload):await self.redis.xadd(topic,{"data":json.dumps(await self.envelope(event_type,payload),separators=(",",":"))},maxlen=100000,approximate=True)
    async def listen(self):
        while True:
            pubsub=self.redis.pubsub();await pubsub.subscribe("scenario.update","position.update")
            try:
                async for message in pubsub.listen():
                    if message["type"]!="message":continue
                    event=json.loads(message["data"])
                    if event.get("source")=="decision-service":continue
                    if event.get("event_type") in {"scenario.created","scenario.updated"}:await self.evaluate(Scenario.model_validate(event["payload"]))
                    elif event.get("event_type") in {"position.closed","order.cancelled","order.rejected"}:
                        self.reserved_signal_id=None;await self.retry_waiting()
            except asyncio.CancelledError:await pubsub.aclose();raise
            except Exception:log.exception("Scenario listener failed");await pubsub.aclose();await asyncio.sleep(2)
    async def recover(self):
        while True:
            try:
                active=await self.db.fetchval("SELECT EXISTS(SELECT 1 FROM orders WHERE status IN ('PENDING','OPEN','SUBMITTING','PARTIALLY_FILLED','CANCEL_REQUESTED','UNKNOWN') UNION ALL SELECT 1 FROM positions WHERE status!='CLOSED')")
                if not active:self.reserved_signal_id=None
                await self.retry_waiting()
                rows=await self.db.fetch("""SELECT s.data FROM scenarios s LEFT JOIN trade_signals ts ON ts.scenario_id=s.id
                  WHERE s.status='ACTIVE' AND s.data->>'setup_type'='ELLIOTT_WAVE3' AND ts.id IS NULL""")
                for row in rows:
                    scenario=Scenario.model_validate(decode_json(row["data"]))
                    if scenario.expires_at>now_ms():await self.evaluate(scenario)
                approvals=await self.db.fetch("""SELECT ts.data FROM trade_signals ts LEFT JOIN orders o ON o.signal_id=ts.id
                  WHERE ts.status IN ('PENDING','APPROVED') AND o.id IS NULL AND ts.created_at>now()-interval '1 day'""")
                for row in approvals:
                    signal=TradeSignal.model_validate(decode_json(row["data"]))
                    if signal.expires_at is None or signal.expires_at>now_ms():await self.assess(signal)
                for scenario in list(self.scenarios.values()):
                    if scenario.status=="ACTIVE" and scenario.expires_at>now_ms():await self.evaluate(scenario)
            except asyncio.CancelledError:raise
            except Exception:log.exception("Decision recovery failed")
            await asyncio.sleep(10)
    async def evaluate(self,scenario:Scenario):
        if scenario.setup_type != "ELLIOTT_WAVE3":
            return None
        if scenario.expires_at <= int(time()*1000):
            return None
        self.scenarios[scenario.id]=scenario
        payload={"scenario_id":scenario.id,"confidence":scenario.confidence}
        await self.pub("scenario.update","scenario.confidence_updated",payload)
        old=self.pending.get(scenario.symbol)
        if old:old.cancel()
        self.pending[scenario.symbol]=asyncio.create_task(self.resolve_after_delay(scenario.symbol))
        return payload
    async def resolve_after_delay(self,symbol):
        await asyncio.sleep(.15);await self.resolve(symbol)
    async def resolve(self,symbol):
        async with self.resolve_lock:return await self._resolve(symbol)
    async def _resolve(self,symbol):
        timestamp=now_ms()
        expired=[item for item in self.scenarios.values() if item.symbol==symbol and item.status=="ACTIVE" and item.expires_at<=timestamp]
        for item in expired:
            item.status="EXPIRED"
            await self.db.execute("UPDATE scenarios SET status='EXPIRED',data=$2::jsonb WHERE id=$1::uuid",item.id,json.dumps(item.model_dump(mode="json")))
        candidates=[x for x in self.scenarios.values() if x.symbol==symbol and x.expires_at>timestamp];selected,rejected=self.resolver.select(candidates)
        for scenario_id,reason in rejected.items():
            item=self.scenarios[scenario_id]
            if item.status!="ACTIVE":continue
            item.status="REJECTED";await self.db.execute("UPDATE scenarios SET status='REJECTED',data=$2::jsonb WHERE id=$1::uuid",item.id,json.dumps(item.model_dump(mode="json")))
            await self.db.execute("INSERT INTO decision_log(scenario_id,decision,reason) VALUES($1::uuid,'REJECTED',$2)",item.id,reason)
            await self.pub("scenario.update","scenario.rejected",{"scenario_id":item.id,"reason":reason,"rejected_at":int(time()*1000)})
        if not selected:return None
        existing=await self.db.fetchrow("SELECT data FROM trade_signals WHERE scenario_id=$1::uuid ORDER BY created_at LIMIT 1",selected.id)
        if existing:
            signal=TradeSignal.model_validate(decode_json(existing["data"]));self.signals[signal.signal_id]=signal
            return signal
        selected.status="SELECTED";await self.db.execute("UPDATE scenarios SET status='SELECTED',data=$2::jsonb WHERE id=$1::uuid",selected.id,json.dumps(selected.model_dump(mode="json")))
        signal=self.resolver.signal(selected);self.signals[signal.signal_id]=signal
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
    async def retry_waiting(self):
        timestamp=now_ms()
        expired=[signal_id for signal_id in self.waiting if signal_id in self.signals
          and self.signals[signal_id].expires_at is not None and self.signals[signal_id].expires_at<=timestamp]
        if expired:
            await self.db.execute("UPDATE trade_signals SET status='EXPIRED' WHERE id=ANY($1::uuid[])",expired)
        candidates=sorted((self.signals[signal_id] for signal_id in self.waiting
          if signal_id in self.signals and (self.signals[signal_id].expires_at is None
          or self.signals[signal_id].expires_at>timestamp)),key=lambda item:item.created_at)
        self.waiting={item.signal_id for item in candidates}
        for signal in candidates:
            decision=await self.assess(signal)
            if decision.approved or decision.rejection_reason=="Another trade is still active":break
    async def assess(self,signal:TradeSignal,capital:float|None=None,ignore_loss_limits:bool=False):
        cfg=await self.config()
        positions=int(await self.redis.scard("positions:open"))
        strategy_row=await self.db.fetchrow("""SELECT tc.config,tc.mode,ta.lot_size,ta.minimum_order_size
          FROM trading_configs tc LEFT JOIN trading_assets ta ON ta.symbol=tc.symbol
          WHERE tc.symbol=$1 AND tc.status='ACTIVE'""",signal.symbol)
        strategy=decode_json(strategy_row["config"]) if strategy_row else {}
        mode=str(strategy_row["mode"]).upper() if strategy_row else "PAPER"
        portfolio_id=config_value(strategy,"portfolioId","portfolio_id",None)
        if not strategy_row:
            decision=RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Trading asset is inactive")
            self.waiting.discard(signal.signal_id)
            await self.db.execute("UPDATE trade_signals SET status='REJECTED' WHERE id=$1::uuid",signal.signal_id)
            return decision
        activated_at=config_value(strategy,"activatedAt","activated_at",0)
        if activated_at and signal.created_at<int(activated_at):
            decision=RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason="Signal predates live activation")
            self.waiting.discard(signal.signal_id)
            await self.db.execute("UPDATE trade_signals SET status='REJECTED' WHERE id=$1::uuid",signal.signal_id)
            return decision
        recent=await self.db.fetch("""SELECT pnl::float8,extract(epoch from closed_at)*1000 AS closed_at_ms
          FROM closed_trades WHERE data->>'execution_mode'=$1
          AND ($2::text IS NULL OR data->>'portfolio_id'=$2) ORDER BY closed_at DESC""",mode,portfolio_id)
        today_start=int(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
        daily=sum(float(row["pnl"]) for row in recent if int(row["closed_at_ms"])>=today_start)
        elliott=config_value(strategy,"elliott","elliott",{}) or {}
        risk_percent=config_value(strategy,"riskPerTradePercent","risk_per_trade_percent",None)
        allocation=config_value(strategy,"portfolioAllocationPercent","portfolio_allocation_percent",100)
        use_margin=bool(config_value(elliott,"useMargin","use_margin",False))
        leverage=int(config_value(strategy,"leverage","leverage",1))
        configured_initial=float(config_value(strategy,"initialCapital","initial_capital",self.default_capital))
        configured_current=float(config_value(strategy,"currentCapital","current_capital",configured_initial))
        reinvest=bool(config_value(elliott,"reinvestProfits","reinvest_profits",True))
        capital=float(capital) if capital is not None else (configured_current if reinvest else min(configured_current,configured_initial))
        capital_ceiling=None
        if mode in {"DEMO","PRODUCTION"}:
            try:
                response=await self.http.get(f"{self.exchange_service_url}/exchange/account/capacity",params={"mode":mode})
                response.raise_for_status();capacity=response.json()
                capital_ceiling=float(capacity["available"])
                if capital_ceiling<=0:raise ValueError("OKX available balance is zero")
            except (httpx.HTTPError,ValueError,KeyError) as exc:
                decision=RiskDecision(signal_id=signal.signal_id,approved=False,rejection_reason=f"OKX capacity unavailable: {exc}")
                self.waiting.add(signal.signal_id)
                await self.db.execute("UPDATE trade_signals SET status='WAITING' WHERE id=$1::uuid",signal.signal_id)
                return decision
        consecutive_losses=0;last_loss_at=None
        for row in recent:
            if row["pnl"]>=0:break
            consecutive_losses+=1
            if last_loss_at is None:last_loss_at=int(row["closed_at_ms"])
        async with self.risk_lock:
            active_orders=await self.db.fetchval("SELECT count(*) FROM orders WHERE status IN ('PENDING','OPEN','SUBMITTING','PARTIALLY_FILLED','CANCEL_REQUESTED')")
            reservation=1 if self.reserved_signal_id and self.reserved_signal_id!=signal.signal_id else 0
            decision=self.risk.calculate(signal,capital,cfg,daily,positions,int(active_orders or 0)+reservation,consecutive_losses,last_loss_at,
              ignore_loss_limits=ignore_loss_limits,risk_percent_override=risk_percent,
              allocation_percent=float(allocation),use_margin=use_margin,leverage_override=leverage,
              lot_size=float(strategy_row["lot_size"]) if strategy_row and strategy_row["lot_size"] else None,
              minimum_order_size=(float(strategy_row["minimum_order_size"])
                                  if strategy_row and strategy_row["minimum_order_size"] else None),
              capital_ceiling=capital_ceiling)
            await self.db.execute("INSERT INTO risk_decisions(signal_id,approved,data) VALUES($1::uuid,$2,$3::jsonb)",signal.signal_id,decision.approved,json.dumps(decision.model_dump(mode="json")))
            if decision.approved:
                self.reserved_signal_id=signal.signal_id;self.waiting.discard(signal.signal_id)
                await self.db.execute("UPDATE trade_signals SET status='APPROVED' WHERE id=$1::uuid",signal.signal_id)
                payload=decision.model_dump();payload["approved_at"]=payload.pop("timestamp");payload.pop("approved");payload.pop("rejection_reason")
                payload["activation_id"]=config_value(strategy,"activationId","activation_id")
                payload["execution_mode"]=mode
                payload["portfolio_id"]=portfolio_id
                await self.stream("trading.command","risk.approved",payload)
            else:
                waiting=decision.rejection_reason=="Another trade is still active"
                if waiting:self.waiting.add(signal.signal_id)
                else:self.waiting.discard(signal.signal_id)
                await self.db.execute("UPDATE trade_signals SET status=$2 WHERE id=$1::uuid",signal.signal_id,"WAITING" if waiting else "REJECTED")
                await self.stream("trading.command","risk.rejected",{"signal_id":signal.signal_id,"rejection_reason":decision.rejection_reason,"calculated_size":decision.position_size,"min_size":cfg.min_position_size,"timestamp":decision.timestamp})
        return decision
    async def simulate_elliott(self,request:SimulatedElliottSignalRequest):
        row=await self.db.fetchrow("SELECT config,mode FROM trading_configs WHERE symbol=$1 AND status='ACTIVE'",request.symbol)
        if not row or str(decode_json(row["config"]).get("strategy","")).upper()!="ELLIOTT":
            raise ValueError("Active Elliott configuration not found")
        mode=str(row["mode"]).upper()
        if mode in {"DEMO","PRODUCTION"}:
            try:
                response=await self.http.get(
                    f"{self.exchange_service_url}/exchange/instruments/{request.symbol}/availability",
                    params={"mode":mode},
                )
                response.raise_for_status();availability=response.json()
            except (httpx.HTTPError,ValueError) as exc:
                raise ValueError(f"Unable to validate {request.symbol} in {mode}: {exc}") from exc
            if not availability.get("available"):
                raise ValueError(availability.get("reason") or f"{request.symbol} is unavailable in {mode}")
        entry=await self.db.fetchval("SELECT close::float8 FROM candles WHERE symbol=$1 ORDER BY ts DESC LIMIT 1",request.symbol)
        if entry is None:raise ValueError("Market price is not available")
        created=now_ms();scenario=simulated_elliott_scenario(request,float(entry),created)
        signal=self.resolver.signal(scenario);self.scenarios[scenario.id]=scenario;self.signals[signal.signal_id]=signal
        await self.db.execute("INSERT INTO scenarios(id,symbol,status,data,created_at) VALUES($1::uuid,$2,'SELECTED',$3::jsonb,to_timestamp($4/1000.0))",scenario.id,scenario.symbol,json.dumps(scenario.model_dump(mode="json")),created)
        await self.pub("scenario.update","scenario.created",scenario)
        await self.db.execute("INSERT INTO trade_signals(id,scenario_id,symbol,status,data,created_at) VALUES($1::uuid,$2::uuid,$3,'PENDING',$4::jsonb,to_timestamp($5/1000.0))",signal.signal_id,scenario.id,signal.symbol,json.dumps(signal.model_dump(mode="json")),signal.created_at)
        ignore_loss_limits=mode in {"PAPER","DEMO"}
        decision=await self.assess(signal,ignore_loss_limits=ignore_loss_limits)
        return {"scenario_id":scenario.id,"signal_id":signal.signal_id,"approved":decision.approved,
                "risk":decision.model_dump(mode="json")}
