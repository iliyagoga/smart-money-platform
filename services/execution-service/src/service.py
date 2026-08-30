from __future__ import annotations
import asyncio,json,logging
from time import time
from uuid import uuid4
import asyncpg
from redis.asyncio import Redis
from .manager import PositionManager
from .models import *
log=logging.getLogger(__name__)
def decode_json(value):return json.loads(value) if isinstance(value,str) else value

class ExecutionService:
    def __init__(self,database_url,redis_url,group="execution-service",consumer="execution-1",mode="paper"):
        self.database_url=database_url;self.redis_url=redis_url;self.group=group;self.consumer=consumer;self.mode=mode
        self.db=None;self.redis=None;self.orders:dict[str,Order]={};self.positions:dict[str,Position]={};self.manager=PositionManager();self.tasks=[]
    async def start(self):
        self.db=await asyncpg.create_pool(self.database_url,min_size=1,max_size=5);self.redis=Redis.from_url(self.redis_url,decode_responses=True);await self.redis.ping()
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS orders(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS positions(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,status text NOT NULL,data jsonb NOT NULL,opened_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS position_state_history(id bigserial PRIMARY KEY,position_id uuid NOT NULL,from_state text,to_state text NOT NULL,trigger text NOT NULL,price numeric,created_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS closed_trades(id uuid PRIMARY KEY,position_id uuid NOT NULL,symbol text NOT NULL,pnl numeric NOT NULL,data jsonb NOT NULL,closed_at timestamptz NOT NULL);
          CREATE TABLE IF NOT EXISTS trading_configs(symbol text PRIMARY KEY,mode text NOT NULL DEFAULT 'SIMULATION',status text NOT NULL DEFAULT 'ACTIVE',config jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now());
          CREATE TABLE IF NOT EXISTS strategy_configurations(id uuid PRIMARY KEY,owner_id text NOT NULL,name text NOT NULL,
            description text NOT NULL DEFAULT '',config jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(owner_id,name));
        """)
        await self.db.execute("UPDATE trading_configs SET mode='PAPER' WHERE mode IN ('SIMULATION','paper')")
        for row in await self.db.fetch("SELECT data FROM orders WHERE status IN ('PENDING','OPEN')"):
            o=Order.model_validate(decode_json(row["data"]));self.orders[o.id]=o
        for row in await self.db.fetch("SELECT data FROM positions WHERE status!='CLOSED'"):
            p=Position.model_validate(decode_json(row["data"]));self.positions[p.id]=p;await self.redis.sadd("positions:open",p.id)
        try:await self.redis.xgroup_create("trading.command",self.group,id="0",mkstream=True)
        except Exception:pass
        self.tasks=[asyncio.create_task(self.consume()),asyncio.create_task(self.listen_candles())]
    async def stop(self):
        for task in self.tasks:task.cancel()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    async def envelope(self,event_type,payload):return {"message_id":str(uuid4()),"correlation_id":str(uuid4()),"timestamp":int(time()*1000),"source":"execution-service","version":"1.0.0","event_type":event_type,"payload":payload}
    async def publish(self,event_type,payload):await self.redis.publish("position.update",json.dumps(await self.envelope(event_type,payload),separators=(",",":")))
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
        row=await self.db.fetchrow("""SELECT ts.data,tc.config,tc.mode FROM trade_signals ts JOIN scenarios s ON s.id=ts.scenario_id
          JOIN trading_configs tc ON tc.symbol=ts.symbol AND tc.status='ACTIVE'
          WHERE ts.id=$1::uuid AND s.data->>'setup_type'='ELLIOTT_WAVE3'""",signal_id)
        if not row:raise ValueError(f"Signal {signal_id} not found")
        s=decode_json(row["data"]);config=decode_json(row["config"]);elliott=config.get("elliott",{});use_margin=elliott.get("useMargin",elliott.get("use_margin",False))
        leverage=int(config.get("leverage",payload.get("leverage",1))) if use_margin else 1
        order=Order(symbol=s["symbol"],side="BUY" if s["direction"]=="LONG" else "SELL",type=s["entry_type"],price=s["entry_price"],quantity=payload["position_size"],stop_loss_price=s["stop_loss_price"],take_profit_prices=s["take_profit_prices"],signal_id=signal_id,target_allocations=s.get("target_allocations",[]),break_even_rule=s.get("break_even_rule","ONE_R"),move_stop_to_break_even_after_target=s.get("move_stop_to_break_even_after_target",1),deduplication_key=s.get("deduplication_key"),leverage=leverage,margin_mode=config.get("marginMode",config.get("margin_mode","cross")),execution_mode=row["mode"])
        await self.create_order(order)
    async def create_order(self,order:Order):
        existing=next((x for x in self.orders.values() if order.signal_id and x.signal_id==order.signal_id),None)
        if existing:return existing
        active_order=any(x.status in {"PENDING","OPEN"} for x in self.orders.values())
        active_position=any(x.status!="CLOSED" for x in self.positions.values())
        if active_order or active_position:raise ValueError("Another trade is still active")
        self.orders[order.id]=order;await self.save_order(order);await self.stream("order.request",order.model_dump(mode="json"))
        if order.execution_mode=="PAPER":
            if order.type=="MARKET":await self.fill(order,order.price or 0)
            else:order.status="OPEN";await self.save_order(order)
        else:order.status="SUBMITTING";await self.save_order(order)
        return order
    async def save_order(self,o):await self.db.execute("INSERT INTO orders(id,signal_id,symbol,status,data,created_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data,updated_at=now()",o.id,o.signal_id,o.symbol,o.status,json.dumps(o.model_dump(mode="json")),o.created_at)
    async def fill(self,o:Order,price:float,exchange_order_id:str|None=None):
        if o.status=="FILLED":return
        o.status="FILLED";o.filled_at=int(time()*1000);o.filled_price=price;o.exchange_order_id=exchange_order_id or f"paper-{o.id}";await self.save_order(o)
        event={"order_id":o.id,"signal_id":o.signal_id,"exchange_order_id":o.exchange_order_id,"symbol":o.symbol,"side":o.side,"price":price,"quantity":o.quantity,"filled_price":price,"filled_quantity":o.quantity,"status":"FILLED","executed_at":o.filled_at};await self.publish("order.executed",event)
        scenario_id=None
        if o.signal_id:
            row=await self.db.fetchrow("""SELECT ts.scenario_id FROM trade_signals ts JOIN scenarios s ON s.id=ts.scenario_id
              WHERE ts.id=$1::uuid AND s.data->>'setup_type'='ELLIOTT_WAVE3'""",o.signal_id);scenario_id=str(row["scenario_id"]) if row else None
            if not scenario_id:raise ValueError("Only Elliott signals can be executed")
        p=Position(signal_id=o.signal_id,scenario_id=scenario_id,order_id=o.id,strategy="ELLIOTT",setup_type="ELLIOTT_WAVE3",symbol=o.symbol,direction="LONG" if o.side=="BUY" else "SHORT",entry_price=price,current_price=price,quantity=o.quantity,initial_quantity=o.quantity,stop_loss_price=o.stop_loss_price,initial_stop_loss_price=o.stop_loss_price,take_profit_prices=list(o.take_profit_prices),target_allocations=list(o.target_allocations),break_even_rule=o.break_even_rule,move_stop_to_break_even_after_target=o.move_stop_to_break_even_after_target)
        self.positions[p.id]=p;await self.redis.sadd("positions:open",p.id);await self.save_position(p,None,"OPENED","ORDER_EXECUTED")
        await self.publish("position.opened",{"position_id":p.id,"signal_id":p.signal_id,"symbol":p.symbol,"direction":p.direction,"entry_price":p.entry_price,"quantity":p.quantity,"leverage":p.leverage,"stop_loss_price":p.stop_loss_price,"take_profit_prices":p.take_profit_prices,"opened_at":p.opened_at})
    async def save_position(self,p,old,new,trigger):
        await self.db.execute("INSERT INTO positions(id,signal_id,symbol,status,data,opened_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO UPDATE SET status=excluded.status,data=excluded.data,updated_at=now()",p.id,p.signal_id,p.symbol,p.status,json.dumps(p.model_dump(mode="json")),p.opened_at)
        if old!=new:await self.db.execute("INSERT INTO position_state_history(position_id,from_state,to_state,trigger,price) VALUES($1::uuid,$2,$3,$4,$5)",p.id,old,new,trigger,p.current_price)
    async def on_candle(self,c:Candle):
        for o in list(self.orders.values()):
            if o.execution_mode=="PAPER" and o.status=="OPEN" and o.symbol==c.symbol and o.price is not None and c.low<=o.price<=c.high:await self.fill(o,o.price)
        for p in list(self.positions.values()):
            if p.status=="CLOSED" or p.symbol!=c.symbol:continue
            old=p.status
            for action,data in self.manager.update(p,c):
                if action=="close":await self.close(p,data["quantity"],data["price"],data["reason"])
                elif action=="partial":await self.close(p,data["quantity"],data["price"],data["reason"])
                else:
                    await self.save_position(p,old,p.status,"ONE_R_REACHED");await self.publish("position.updated",{"position_id":p.id,"changes":data,"current_price":p.current_price,"unrealized_pnl":p.unrealized(),"unrealized_pnl_percent":p.unrealized()/max(p.entry_price*p.quantity,1e-12)*100,"updated_at":int(time()*1000)})
            if p.status!="CLOSED":await self.save_position(p,p.status,p.status,"PRICE_UPDATE")
    async def close(self,p:Position,quantity:float,price:float,reason:str):
        qty=min(quantity,p.quantity);pnl=(price-p.entry_price)*qty*(1 if p.direction=="LONG" else -1);p.realized_pnl+=pnl;p.quantity-=qty
        if p.quantity>1e-12:
            p.partial_takes.append({"price":price,"quantity":qty,"time":int(time()*1000),"pnl":pnl})
            if (p.break_even_rule=="AFTER_TARGET" and p.move_stop_to_break_even_after_target is not None
                    and p.targets_hit>=p.move_stop_to_break_even_after_target):
                p.stop_loss_price=p.entry_price;p.protected=True
            p.status="PARTIAL_TP";await self.save_position(p,"OPENED",p.status,reason)
            await self.publish("position.partial_closed",{"position_id":p.id,"closed_quantity":qty,"closing_price":price,"remaining_quantity":p.quantity,"realized_pnl":pnl,"new_stop_loss_price":p.stop_loss_price,"timestamp":int(time()*1000)})
        else:
            old=p.status;p.status="CLOSED";p.closed_at=int(time()*1000);await self.redis.srem("positions:open",p.id);await self.save_position(p,old,"CLOSED",reason)
            duration=max(0,(p.closed_at-p.opened_at)//1000);risk_per_unit=abs(p.entry_price-p.initial_stop_loss_price) if p.initial_stop_loss_price is not None else 0;initial_risk=risk_per_unit*p.initial_quantity
            payload={"position_id":p.id,"signal_id":p.signal_id,"scenario_id":p.scenario_id,"strategy":p.strategy,"setup_type":p.setup_type,"symbol":p.symbol,"direction":p.direction,"entry_price":p.entry_price,"initial_stop_loss_price":p.initial_stop_loss_price,"exit_price":price,"quantity":p.initial_quantity,"pnl":p.realized_pnl,"pnl_percent":p.realized_pnl/max(p.entry_price*p.initial_quantity,1e-12)*100,"r_multiple":p.realized_pnl/initial_risk if initial_risk>0 else None,"reason":reason,"duration_seconds":duration,"max_unrealized_pnl":p.max_unrealized_pnl,"max_unrealized_loss":p.max_unrealized_loss,"closed_at":p.closed_at}
            await self.db.execute("INSERT INTO closed_trades(id,position_id,symbol,pnl,data,closed_at) VALUES($1::uuid,$2::uuid,$3,$4,$5::jsonb,to_timestamp($6/1000.0)) ON CONFLICT(id) DO NOTHING",str(uuid4()),p.id,p.symbol,p.realized_pnl,json.dumps(payload),p.closed_at);await self.publish("position.closed",payload)
        return qty,p.quantity,pnl
    async def on_exchange_order(self,payload):
        order=self.orders.get(payload.get("order_id"))
        if not order:return
        status=payload.get("status","").upper();order.exchange_order_id=payload.get("exchange_order_id") or order.exchange_order_id
        if status=="FILLED" and order.status!="FILLED":
            price=float(payload.get("filled_price") or order.price or 0)
            if price<=0:raise ValueError("Filled order has no execution price")
            await self.fill(order,price,order.exchange_order_id)
        elif status in {"OPEN","PARTIALLY_FILLED","CANCELLED","REJECTED"}:
            order.status=status;await self.save_order(order)
    async def request_cancel(self,order:Order):
        if order.status=="FILLED":raise ValueError("Filled order cannot be cancelled")
        if order.execution_mode=="PAPER":order.status="CANCELLED";await self.save_order(order)
        else:
            order.status="CANCEL_REQUESTED";await self.save_order(order)
            await self.stream("order.cancel_requested",{"order_id":order.id,"symbol":order.symbol,"exchange_order_id":order.exchange_order_id})
        return order
