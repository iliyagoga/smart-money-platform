from __future__ import annotations
import asyncio,json,logging
from math import ceil,floor
from time import time
from uuid import uuid4
import asyncpg,httpx
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from .manager import PositionManager,fee_adjusted_break_even
from .models import *
log=logging.getLogger(__name__)
ACTIVE_ORDER_STATUSES={"PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","CANCEL_REQUESTED"}
def decode_json(value):return json.loads(value) if isinstance(value,str) else value
def actionable_candle(candle:Candle,created_at:int):
    # Several timeframes describe the same market interval. Applying an H4/M15
    # high or low to a newly opened position reuses price action from before entry.
    return candle.timeframe=="M1" and candle.timestamp+60_000>created_at

class ExecutionService:
    def __init__(self,database_url,redis_url,group="execution-service",consumer="execution-1",mode="paper",
                 exchange_service_url="http://exchange-gateway:8070"):
        self.database_url=database_url;self.redis_url=redis_url;self.group=group;self.consumer=consumer;self.mode=mode
        self.exchange_service_url=exchange_service_url.rstrip("/");self.http=None
        self.db=None;self.redis=None;self.orders:dict[str,Order]={};self.positions:dict[str,Position]={};self.manager=PositionManager();self.tasks=[]
    async def start(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        self.http=httpx.AsyncClient(timeout=10)
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS orders(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS positions(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,opened_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS position_state_history(id bigserial PRIMARY KEY,position_id uuid NOT NULL,from_state text,to_state text NOT NULL,trigger text NOT NULL,price numeric,created_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS closed_trades(id uuid PRIMARY KEY,position_id uuid NOT NULL,symbol text NOT NULL,pnl numeric NOT NULL,data jsonb NOT NULL,closed_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS trading_configs(symbol text PRIMARY KEY,mode text NOT NULL DEFAULT 'SIMULATION',status text NOT NULL DEFAULT 'ACTIVE',config jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS strategy_configurations(id uuid PRIMARY KEY,owner_id text NOT NULL,name text NOT NULL,
            description text NOT NULL DEFAULT '',config jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,name));
          CREATE TABLE IF NOT EXISTS portfolios(id uuid PRIMARY KEY,owner_id text NOT NULL,name text NOT NULL,
            description text NOT NULL DEFAULT '',assets jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,name));
        """)
        await self.db.execute("UPDATE trading_configs SET mode='PAPER' WHERE mode IN ('SIMULATION','paper')")
        for row in await self.db.fetch("""SELECT o.data,eo.payload->>'error' AS rejection_reason
          FROM orders o LEFT JOIN exchange_orders eo ON eo.local_order_id=o.id
          ORDER BY o.created_at DESC LIMIT 1000"""):
            o=Order.model_validate(decode_json(row["data"]))
            if o.status=="REJECTED" and not o.rejection_reason:o.rejection_reason=row["rejection_reason"]
            self.orders[o.id]=o
        for row in await self.db.fetch("SELECT data FROM positions WHERE status!='CLOSED'"):
            p=Position.model_validate(decode_json(row["data"]));self.positions[p.id]=p;await self.redis.sadd("positions:open",p.id)
        try:await self.redis.xgroup_create("trading.command",self.group,id="0",mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):raise
        self.tasks=[asyncio.create_task(self.consume()),asyncio.create_task(self.listen_candles())]
    async def stop(self):
        for task in self.tasks:task.cancel()
        if self.redis:await self.redis.aclose()
        if self.http:await self.http.aclose()
        if self.db:await self.db.close()

    async def validate_execution_mode(self,symbol:str,mode:str):
        if mode=="PAPER":return
        try:
            response=await self.http.get(
                f"{self.exchange_service_url}/exchange/instruments/{symbol}/availability",params={"mode":mode})
            response.raise_for_status();availability=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            raise ValueError(f"Unable to validate {symbol} in {mode}: {exc}") from exc
        if not availability.get("available"):
            raise ValueError(availability.get("reason") or f"{symbol} is unavailable in {mode}")
    @staticmethod
    def validate_live_config(config:dict,mode:str):
        if mode=="PAPER":return
        elliott=config.get("elliott",{})
        if not isinstance(elliott,dict):raise ValueError("elliott config must be an object")
        def value(camel,snake,default):return elliott.get(camel,elliott.get(snake,default))
        if int(value("takeProfitCount","take_profit_count",2))!=1:
            raise ValueError("DEMO/PRODUCTION currently supports exactly one take-profit target")
        if bool(value("breakEvenAtOneR","break_even_at_one_r",False)):
            raise ValueError("DEMO/PRODUCTION does not yet support automatic break-even amendments")
        supported_entries={"CHOCH_RETRACE","WAVE1_BREAK_RETRACE","DISPLACEMENT_RETRACE"}
        if str(value("entryModel","entry_model","CHOCH_RETRACE")) not in supported_entries:
            raise ValueError("DEMO/PRODUCTION currently supports LIMIT entry models only")
    async def envelope(self,event_type,payload):return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"execution-service","version":"1.0.0","event_type":event_type,"payload":payload}
    async def publish(self,event_type,payload):await self.redis.publish("position.update",json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
    async def publish_channel(self,channel,event_type,payload):
        await self.redis.publish(channel,json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
    async def stream(self,event_type,payload):await self.redis.xadd("execution.command",{"data":json.dumps(await self.envelope(event_type,payload),separators=(",",":"))},maxlen=100000,approximate=True)
    async def consume(self):
        await self.consume_pending()
        while True:
            try:
                batches=await self.redis.xreadgroup(self.group,self.consumer,{"trading.command":">"},count=10,block=2000)
                for _,messages in batches:
                    for message_id,fields in messages:
                        try:
                            event=json.loads(fields["data"])
                            if event["event_type"]=="risk.approved":await self.on_approved(event["payload"])
                            elif event["event_type"]=="exchange.order_updated":await self.on_exchange_order(event["payload"])
                            await self.redis.xack("trading.command",self.group,message_id)
                        except Exception:log.exception("Command %s failed",message_id)
            except asyncio.CancelledError:raise
            except Exception:log.exception("Stream consumer failed");await asyncio.sleep(2)
    async def consume_pending(self):
        while True:
            batches=await self.redis.xreadgroup(self.group,self.consumer,{"trading.command":"0"},count=50)
            if not batches or not batches[0][1]:return
            for _,messages in batches:
                for message_id,fields in messages:
                    try:
                        event=json.loads(fields["data"])
                        if event["event_type"]=="risk.approved":await self.on_approved(event["payload"])
                        elif event["event_type"]=="exchange.order_updated":await self.on_exchange_order(event["payload"])
                        await self.redis.xack("trading.command",self.group,message_id)
                    except Exception:log.exception("Pending command %s failed",message_id);return
    async def listen_candles(self):
        while True:
            pubsub=self.redis.pubsub();await pubsub.subscribe("candle.update")
            try:
                async for msg in pubsub.listen():
                    if msg["type"]=="message":await self.on_candle(Candle.model_validate(json.loads(msg["data"])["payload"]))
            except asyncio.CancelledError:await pubsub.aclose();raise
            except Exception:log.exception("Candle listener failed");await pubsub.aclose();await asyncio.sleep(2)
    async def on_approved(self,payload):
        signal_id=payload["signal_id"]
        if any(x.signal_id==signal_id for x in self.orders.values()):return
        row=await self.db.fetchrow("""SELECT ts.data,tc.config,tc.mode,ta.tick_size,ta.lot_size,ta.minimum_order_size,ta.maker_fee_rate,ta.taker_fee_rate,ta.funding_rate FROM trade_signals ts JOIN scenarios s ON s.id=ts.scenario_id
          JOIN trading_configs tc ON tc.symbol=ts.symbol AND tc.status='ACTIVE'
          LEFT JOIN trading_assets ta ON ta.symbol=ts.symbol
          WHERE ts.id=$1::uuid AND s.data->>'setup_type'='ELLIOTT_WAVE3'""",signal_id)
        if not row:raise ValueError(f"Signal {signal_id} not found")
        s=decode_json(row["data"]);config=decode_json(row["config"]);elliott=config.get("elliott",{});use_margin=elliott.get("useMargin",elliott.get("use_margin",False))
        leverage=int(config.get("leverage",payload.get("leverage",1))) if use_margin else 1
        maker=abs(float(row["maker_fee_rate"]))*100 if row["maker_fee_rate"] is not None else float(config.get("makerFeePercent",config.get("maker_fee_percent",config.get("feePercent",config.get("fee_percent",0)))))
        taker=abs(float(row["taker_fee_rate"]))*100 if row["taker_fee_rate"] is not None else float(config.get("takerFeePercent",config.get("taker_fee_percent",config.get("feePercent",config.get("fee_percent",0)))))
        funding=float(row["funding_rate"])*300 if row["funding_rate"] is not None else float(config.get("fundingPercentPerDay",config.get("funding_percent_per_day",0)))
        order=Order(symbol=s["symbol"],side="BUY" if s["direction"]=="LONG" else "SELL",type=s["entry_type"],price=s["entry_price"],quantity=payload["position_size"],stop_loss_price=s["stop_loss_price"],take_profit_prices=s["take_profit_prices"],signal_id=signal_id,target_allocations=s.get("target_allocations",[]),target_rrs=s.get("target_rrs",[]),break_even_rule=s.get("break_even_rule","ONE_R"),move_stop_to_break_even_after_target=s.get("move_stop_to_break_even_after_target",1),deduplication_key=s.get("deduplication_key"),leverage=leverage,margin_mode=config.get("marginMode",config.get("margin_mode","cross")),execution_mode=row["mode"],expires_at=s.get("expires_at"),slippage_percent=float(config.get("slippagePercent",config.get("slippage_percent",0))),tick_size=float(row["tick_size"] or config.get("tickSize",config.get("tick_size",.01))),lot_size=float(row["lot_size"] or config.get("lotSize",config.get("lot_size",.000001))),minimum_order_size=float(row["minimum_order_size"] or config.get("minimumOrderSize",config.get("minimum_order_size",.000001))),volume_participation_percent=float(config.get("volumeParticipationPercent",config.get("volume_participation_percent",5))),maker_fee_percent=maker,taker_fee_percent=taker,funding_percent_per_day=funding,funding_interval_hours=int(config.get("fundingIntervalHours",config.get("funding_interval_hours",8))),maintenance_margin_percent=float(config.get("maintenanceMarginPercent",config.get("maintenance_margin_percent",.5))),liquidation_fee_percent=float(config.get("liquidationFeePercent",config.get("liquidation_fee_percent",.5))))
        await self.create_order(order)
    async def create_order(self,order:Order):
        existing=next((x for x in self.orders.values() if order.signal_id and x.signal_id==order.signal_id),None)
        if existing:return existing
        active_order=any(x.status in ACTIVE_ORDER_STATUSES for x in self.orders.values())
        active_position=any(x.status!="CLOSED" for x in self.positions.values())
        if active_order or active_position:raise ValueError("Another trade is still active")
        self.orders[order.id]=order;await self.save_order(order)
        if order.execution_mode=="PAPER":
            order.status="OPEN";await self.save_order(order)
        elif order.type=="STOP":
            # OKX regular orders do not support STOP as an order type. Keep the
            # trigger locally, then submit a MARKET order when a new M1 candle crosses it.
            order.status="OPEN";await self.save_order(order)
        else:
            order.status="SUBMITTING";await self.save_order(order);await self.stream("order.request",order.model_dump(mode="json"))
        return order
    async def request_position_close(self,p:Position,quantity:float,reason:str="MANUAL"):
        quantity=min(quantity,p.quantity)
        existing=next((item for item in self.orders.values() if item.reduce_only
          and item.position_id==p.id and item.status in ACTIVE_ORDER_STATUSES),None)
        if existing:return existing
        order=Order(symbol=p.symbol,side="SELL" if p.direction=="LONG" else "BUY",type="MARKET",
          price=p.current_price,quantity=quantity,execution_mode=p.execution_mode,margin_mode=p.margin_mode,
          leverage=p.leverage,tick_size=p.tick_size,lot_size=p.lot_size,
          minimum_order_size=p.minimum_order_size,maker_fee_percent=p.maker_fee_percent,
          taker_fee_percent=p.taker_fee_percent,reduce_only=True,position_id=p.id,close_reason=reason)
        self.orders[order.id]=order;order.status="SUBMITTING";await self.save_order(order)
        await self.stream("order.request",order.model_dump(mode="json"));return order
    async def save_order(self,o):
        await self.db.execute("INSERT INTO orders(id,signal_id,symbol,status,data,created_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data,updated_at=now()",o.id,o.signal_id,o.symbol,o.status,json.dumps(o.model_dump(mode="json")),o.created_at)
        await self.publish("order.updated",{"order_id":o.id,"signal_id":o.signal_id,"symbol":o.symbol,
          "status":o.status,"rejection_reason":o.rejection_reason})
    async def update_current_capital(self,symbol,pnl):
        row=await self.db.fetchrow("SELECT config FROM trading_configs WHERE symbol=$1 AND status='ACTIVE'",symbol)
        if not row:return
        config=decode_json(row["config"]);elliott=config.get("elliott",{})
        initial=float(config.get("initialCapital",config.get("initial_capital",0)))
        current=float(config.get("currentCapital",config.get("current_capital",initial)))
        config["currentCapital"]=max(0,current+float(pnl));config.pop("current_capital",None)
        await self.db.execute("UPDATE trading_configs SET config=$2::jsonb,updated_at=now() WHERE symbol=$1",symbol,json.dumps(config))
        await self.publish_channel("trading.config","trading.config.capital_updated",{
          "symbol":symbol,"current_capital":config["currentCapital"],"realized_pnl":float(pnl)})
    async def fill(self,o:Order,price:float,exchange_order_id:str|None=None,executed_at:int|None=None,
                   cumulative_quantity:float|None=None,final:bool=True,cumulative_price:float|None=None):
        cumulative=min(float(cumulative_quantity) if cumulative_quantity is not None else o.quantity,o.quantity)
        filled_at=executed_at or int(time()*1000)
        if o.reduce_only:
            position=self.positions.get(o.position_id or "")
            processed=max(o.filled_quantity,position.exit_filled_quantities.get(o.id,0) if position else 0)
            delta=max(0,cumulative-processed)
            o.filled_quantity=max(o.filled_quantity,cumulative);o.filled_price=cumulative_price or price;o.filled_at=filled_at
            o.exchange_order_id=exchange_order_id or o.exchange_order_id
            o.status="FILLED" if final or cumulative+1e-12>=o.quantity else "PARTIALLY_FILLED"
            if delta>1e-12 and position and position.status!="CLOSED":
                position.exit_filled_quantities[o.id]=cumulative
                await self.close(position,delta,price,o.close_reason or "MANUAL",exchange_fill=True)
            await self.save_order(o);return
        existing_position=next((item for item in self.positions.values() if item.order_id==o.id and item.status!="CLOSED"),None)
        processed=max(o.filled_quantity,existing_position.initial_quantity if existing_position else 0)
        delta=max(0,cumulative-processed)
        if delta<=1e-12:
            changed=cumulative>o.filled_quantity+1e-12 or (final and o.status!="FILLED")
            o.filled_quantity=max(o.filled_quantity,cumulative);o.filled_price=cumulative_price or o.filled_price or price
            o.filled_at=filled_at;o.exchange_order_id=exchange_order_id or o.exchange_order_id
            o.status="FILLED" if final or cumulative+1e-12>=o.quantity else "PARTIALLY_FILLED"
            if changed:await self.save_order(o)
            return
        scenario_id=None
        if existing_position:scenario_id=existing_position.scenario_id
        elif o.signal_id:
            row=await self.db.fetchrow("""SELECT ts.scenario_id FROM trade_signals ts JOIN scenarios s ON s.id=ts.scenario_id
              WHERE ts.id=$1::uuid AND s.data->>'setup_type'='ELLIOTT_WAVE3'""",o.signal_id);scenario_id=str(row["scenario_id"]) if row else None
            if not scenario_id:raise ValueError("Only Elliott signals can be executed")
        if o.execution_mode=="PAPER" and o.type=="MARKET" and o.stop_loss_price is not None and o.target_rrs:
            side=1 if o.side=="BUY" else -1;risk=abs(price-o.stop_loss_price)
            o.take_profit_prices=[(ceil((price+side*risk*rr)/o.tick_size) if side==1
                                    else floor((price+side*risk*rr)/o.tick_size))*o.tick_size
                                   for rr in o.target_rrs]
        entry_fee=o.maker_fee_percent if o.type=="LIMIT" else o.taker_fee_percent
        if existing_position:
            before=existing_position.model_copy(deep=True)
            total=existing_position.quantity+delta
            existing_position.entry_price=(existing_position.entry_price*existing_position.quantity+price*delta)/total
            existing_position.current_price=price;existing_position.quantity=total;existing_position.initial_quantity+=delta
            try:await self.save_position(existing_position,existing_position.status,existing_position.status,"ORDER_PARTIAL_FILL")
            except Exception:self.positions[existing_position.id]=before;raise
            position=existing_position
        else:
            position=Position(signal_id=o.signal_id,scenario_id=scenario_id,order_id=o.id,
              strategy="ELLIOTT",setup_type="ELLIOTT_WAVE3",symbol=o.symbol,
              direction="LONG" if o.side=="BUY" else "SHORT",entry_price=price,current_price=price,
              quantity=delta,initial_quantity=delta,leverage=o.leverage,
              execution_mode=o.execution_mode,margin_mode=o.margin_mode,
              stop_loss_price=o.stop_loss_price,initial_stop_loss_price=o.stop_loss_price,
              take_profit_prices=list(o.take_profit_prices),target_allocations=list(o.target_allocations),
              break_even_rule=o.break_even_rule,
              move_stop_to_break_even_after_target=o.move_stop_to_break_even_after_target,
              entry_fee_percent=entry_fee,maker_fee_percent=o.maker_fee_percent,
              taker_fee_percent=o.taker_fee_percent,slippage_percent=o.slippage_percent,
              tick_size=o.tick_size,lot_size=o.lot_size,minimum_order_size=o.minimum_order_size,
              funding_percent_per_day=o.funding_percent_per_day,
              funding_interval_hours=o.funding_interval_hours,
              maintenance_margin_percent=o.maintenance_margin_percent,
              liquidation_fee_percent=o.liquidation_fee_percent,last_funding_at=filled_at)
            await self.save_position(position,None,"OPENED","ORDER_EXECUTED")
            self.positions[position.id]=position;await self.redis.sadd("positions:open",position.id)
        base_average=(o.filled_price if o.filled_quantity>=processed-1e-12 else before.entry_price)
        o.filled_quantity=cumulative;o.filled_price=cumulative_price or ((base_average or 0)*processed+price*delta)/cumulative
        o.status="FILLED" if final or cumulative+1e-12>=o.quantity else "PARTIALLY_FILLED"
        o.filled_at=filled_at;o.exchange_order_id=exchange_order_id or o.exchange_order_id or f"paper-{o.id}"
        await self.save_order(o)
        event={"order_id":o.id,"signal_id":o.signal_id,"exchange_order_id":o.exchange_order_id,
          "symbol":o.symbol,"side":o.side,"price":price,"quantity":delta,"filled_price":price,
          "filled_quantity":cumulative,"status":o.status,"executed_at":o.filled_at};await self.publish("order.executed",event)
        event_type="position.updated" if existing_position else "position.opened"
        await self.publish(event_type,{"position_id":position.id,"signal_id":position.signal_id,
          "symbol":position.symbol,"direction":position.direction,"entry_price":position.entry_price,
          "quantity":position.quantity,"leverage":position.leverage,"stop_loss_price":position.stop_loss_price,
          "take_profit_prices":position.take_profit_prices,"updated_at":filled_at,"opened_at":position.opened_at})
    async def save_position(self,p,old,new,trigger):
        await self.db.execute("INSERT INTO positions(id,signal_id,symbol,status,data,opened_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data,updated_at=now()",p.id,p.signal_id,p.symbol,p.status,json.dumps(p.model_dump(mode="json")),p.opened_at)
        if old!=new:await self.db.execute("INSERT INTO position_state_history(position_id,from_state,to_state,trigger,price) VALUES($1::uuid,$2,$3,$4,$5)",p.id,old,new,trigger,p.current_price)
    async def on_candle(self,c:Candle):
        for o in list(self.orders.values()):
            if o.status not in {"OPEN","PENDING","SUBMITTING"} or o.symbol!=c.symbol:continue
            if o.expires_at is not None and c.timestamp>o.expires_at:
                await self.request_cancel(o);continue
            if not actionable_candle(c,o.created_at):continue
            side=1 if o.side=="BUY" else -1
            if o.execution_mode!="PAPER":
                if o.type=="STOP" and o.price is not None and (c.high>=o.price if o.side=="BUY" else c.low<=o.price):
                    o.type="MARKET";o.status="SUBMITTING";await self.save_order(o);await self.stream("order.request",o.model_dump(mode="json"))
                continue
            fill_price=None
            if o.type=="MARKET":
                fill_price=c.open*(1+side*o.slippage_percent/100)
            elif o.price is not None:
                touched=((c.low<=o.price if o.side=="BUY" else c.high>=o.price) if o.type=="LIMIT"
                         else (c.high>=o.price if o.side=="BUY" else c.low<=o.price))
                if touched:fill_price=o.price
            if fill_price is None:continue
            capacity=c.volume*o.volume_participation_percent/100
            quantity=floor((min(o.quantity,capacity)+o.lot_size*1e-9)/o.lot_size)*o.lot_size
            if quantity+1e-12<o.minimum_order_size:
                await self.request_cancel(o);continue
            o.quantity=quantity;await self.fill(o,fill_price,executed_at=c.timestamp)
        for p in list(self.positions.values()):
            if p.status=="CLOSED" or p.symbol!=c.symbol or not actionable_candle(c,p.opened_at):continue
            if p.execution_mode!="PAPER":
                p.current_price=c.close;unrealized=p.unrealized()
                p.max_unrealized_pnl=max(p.max_unrealized_pnl,unrealized)
                p.max_unrealized_loss=min(p.max_unrealized_loss,unrealized)
                await self.save_position(p,p.status,p.status,"PRICE_UPDATE")
                await self.publish("position.updated",{"position_id":p.id,"symbol":p.symbol,
                  "current_price":p.current_price,"unrealized_pnl":unrealized,
                  "unrealized_pnl_percent":unrealized/max(p.entry_price*p.quantity,1e-12)*100,
                  "updated_at":int(time()*1000)})
                continue
            interval=p.funding_interval_hours*3_600_000
            available_at=c.timestamp+60_000
            funding_events=max(0,(available_at-(p.last_funding_at or p.opened_at))//interval)
            if funding_events:
                funding=p.entry_price*p.quantity*p.funding_percent_per_day/100*p.funding_interval_hours/24*funding_events
                signed=funding*(1 if p.direction=="LONG" else -1)
                p.realized_pnl-=signed;p.funding+=signed;p.last_funding_at=(p.last_funding_at or p.opened_at)+funding_events*interval
            old=p.status
            for action,data in self.manager.update(p,c):
                if action=="close":await self.close(p,data["quantity"],data["price"],data["reason"])
                elif action=="partial":await self.close(p,data["quantity"],data["price"],data["reason"])
                else:
                    await self.save_position(p,old,p.status,"ONE_R_REACHED");await self.publish("position.updated",{"position_id":p.id,"changes":data,"current_price":p.current_price,"unrealized_pnl":p.unrealized(),"unrealized_pnl_percent":p.unrealized()/max(p.entry_price*p.quantity,1e-12)*100,"updated_at":int(time()*1000)})
            if p.status!="CLOSED":await self.save_position(p,p.status,p.status,"PRICE_UPDATE")
    async def close(self,p:Position,quantity:float,price:float,reason:str,exchange_fill:bool=False):
        qty=min(quantity,p.quantity);side=1 if p.direction=="LONG" else -1
        target=reason in {"TAKE_PROFIT","FIXED_RR_TARGET"}
        exit_price=price if exchange_fill or target else price*(1-side*p.slippage_percent/100)
        exit_fee_rate=(p.taker_fee_percent if exchange_fill else
                       p.maker_fee_percent if target else p.taker_fee_percent)/100
        fees=(p.entry_price*qty*p.entry_fee_percent/100+exit_price*qty*exit_fee_rate)
        liquidation_fee=exit_price*qty*p.liquidation_fee_percent/100 if reason=="LIQUIDATION" else 0
        fees+=liquidation_fee
        pnl=(exit_price-p.entry_price)*qty*side-fees;p.realized_pnl+=pnl;p.fees+=fees;p.quantity-=qty
        if p.quantity>1e-12:
            p.partial_takes.append({"price":exit_price,"quantity":qty,"time":int(time()*1000),"pnl":pnl,"fees":fees})
            if (p.break_even_rule=="AFTER_TARGET" and p.move_stop_to_break_even_after_target is not None
                    and p.targets_hit>=p.move_stop_to_break_even_after_target):
                p.stop_loss_price=fee_adjusted_break_even(p);p.protected=True
            p.status="PARTIAL_TP";await self.save_position(p,"OPENED",p.status,reason)
            await self.publish("position.partial_closed",{"position_id":p.id,"closed_quantity":qty,"closing_price":exit_price,"remaining_quantity":p.quantity,"realized_pnl":pnl,"fees":fees,"new_stop_loss_price":p.stop_loss_price,"timestamp":int(time()*1000)})
        else:
            old=p.status;p.status="CLOSED";p.closed_at=int(time()*1000);await self.redis.srem("positions:open",p.id);await self.save_position(p,old,"CLOSED",reason)
            duration=max(0,(p.closed_at-p.opened_at)//1000);risk_per_unit=abs(p.entry_price-p.initial_stop_loss_price) if p.initial_stop_loss_price is not None else 0;initial_risk=risk_per_unit*p.initial_quantity
            margin=p.entry_price*p.initial_quantity/(p.leverage if p.leverage>1 else 1)
            payload={"position_id":p.id,"signal_id":p.signal_id,"scenario_id":p.scenario_id,"strategy":p.strategy,"setup_type":p.setup_type,"symbol":p.symbol,"direction":p.direction,"entry_price":p.entry_price,"initial_stop_loss_price":p.initial_stop_loss_price,"exit_price":exit_price,"quantity":p.initial_quantity,"pnl":p.realized_pnl,"pnl_percent":p.realized_pnl/max(margin,1e-12)*100,"fees":p.fees,"funding":p.funding,"r_multiple":p.realized_pnl/initial_risk if initial_risk>0 else None,"reason":reason,"duration_seconds":duration,"max_unrealized_pnl":p.max_unrealized_pnl,"max_unrealized_loss":p.max_unrealized_loss,"closed_at":p.closed_at}
            await self.db.execute("INSERT INTO closed_trades(id,position_id,symbol,pnl,data,closed_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO NOTHING",str(uuid4()),p.id,p.symbol,p.realized_pnl,json.dumps(payload),p.closed_at)
            await self.update_current_capital(p.symbol,p.realized_pnl);await self.publish("position.closed",payload)
        return qty,p.quantity,pnl
    async def on_exchange_order(self,payload):
        order=self.orders.get(payload.get("order_id"))
        if not order:return
        status=payload.get("status","").upper();order.exchange_order_id=payload.get("exchange_order_id") or order.exchange_order_id
        if payload.get("position_exit"):
            if status not in {"FILLED","PARTIALLY_FILLED"}:return
            position=next((item for item in self.positions.values()
                           if item.order_id==order.id and item.status!="CLOSED"),None)
            if not position:return
            price=float(payload.get("filled_price") or 0)
            if price<=0:raise ValueError("Protective exit has no execution price")
            cumulative=float(payload.get("filled_quantity") or (position.quantity if status=="FILLED" else 0))
            delta=max(0,cumulative-position.protective_filled_quantity)
            if delta<=1e-12:return
            incremental_price=max(0,(price*cumulative-position.protective_filled_notional)/delta)
            if incremental_price<=0:raise ValueError("Protective exit has an invalid cumulative average price")
            position.protective_filled_quantity=cumulative
            position.protective_filled_notional=price*cumulative
            profitable=(incremental_price>=position.entry_price if position.direction=="LONG" else incremental_price<=position.entry_price)
            reason="FIXED_RR_TARGET" if profitable else "STRUCTURAL_STOP"
            await self.close(position,delta,incremental_price,reason,exchange_fill=True)
            return
        if status in {"FILLED","PARTIALLY_FILLED"}:
            price=float(payload.get("filled_price") or order.price or 0)
            if price<=0:raise ValueError("Filled order has no execution price")
            cumulative=float(payload.get("filled_quantity") or (order.quantity if status=="FILLED" else 0))
            delta=max(0,cumulative-order.filled_quantity)
            incremental_price=(price if delta<=1e-12 else
              (price*cumulative-(order.filled_price or price)*order.filled_quantity)/delta)
            if incremental_price<=0:raise ValueError("Filled order has an invalid cumulative average price")
            await self.fill(order,incremental_price,order.exchange_order_id,
              cumulative_quantity=cumulative,final=status=="FILLED")
        elif status in {"OPEN","CANCELLED","REJECTED"}:
            order.status=status
            if status=="REJECTED":order.rejection_reason=payload.get("reason") or "Exchange rejected the order"
            await self.save_order(order)
            if status in {"CANCELLED","REJECTED"}:
                await self.publish(f"order.{status.lower()}",{"order_id":order.id,"signal_id":order.signal_id,
                  "symbol":order.symbol,"reason":order.rejection_reason})
    async def request_cancel(self,order:Order):
        if order.status=="FILLED":raise ValueError("Filled order cannot be cancelled")
        if order.execution_mode=="PAPER" or order.exchange_order_id is None:
            order.status="CANCELLED";await self.save_order(order)
            await self.publish("order.cancelled",{"order_id":order.id,"signal_id":order.signal_id,"symbol":order.symbol})
        else:
            order.status="CANCEL_REQUESTED";await self.save_order(order)
            await self.stream("order.cancel_requested",{"order_id":order.id,"symbol":order.symbol,"exchange_order_id":order.exchange_order_id})
        return order
