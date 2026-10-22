import asyncio,json,logging,random
from time import monotonic,time
from uuid import uuid4
import asyncpg,httpx,websockets
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlencode
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from .okx import TIMEFRAMES,REVERSE_TIMEFRAMES,auth_headers,book,candle,trade,ws_login

log=logging.getLogger(__name__)

class ExchangeAmbiguousError(ValueError):
    """The exchange may have accepted a request whose response was lost."""

class TradingNotReadyError(ValueError):
    """The request is safe to retry because no exchange order was submitted."""

TIMEFRAME_MILLISECONDS={"M1":60_000,"M5":300_000,"M15":900_000,"M30":1_800_000,"H1":3_600_000,"H4":14_400_000,"D1":86_400_000}

def incremental_start(timeframe,latest,fallback):
    return latest+TIMEFRAME_MILLISECONDS[timeframe] if latest is not None else fallback

def price_to_tick(value,tick_size):
    price=Decimal(str(value));tick=Decimal(str(tick_size))
    return format((price/tick).quantize(Decimal("1"),rounding=ROUND_HALF_UP)*tick,"f")

def okx_ack(data,operation):
    item=(data or [{}])[0]
    if item.get("sCode","0")!="0":
        details={"sCode":item.get("sCode"),"sMsg":item.get("sMsg"),"ordId":item.get("ordId")}
        raise ValueError(f"OKX {operation} rejected: {json.dumps(details,separators=(',',':'))}")
    return item

def okx_error_details(result):
    details={"code":result.get("code"),"msg":result.get("msg")}
    item=(result.get("data") or [{}])[0]
    if isinstance(item,dict):
        details.update({key:item.get(key) for key in ("sCode","sMsg","ordId") if item.get(key) not in (None,"")})
    return details

def instrument_spec(item):
    tick=Decimal(item["tickSz"]);contract_value=Decimal(item.get("ctVal") or "1")
    lot=Decimal(item["lotSz"])*contract_value;minimum=Decimal(item["minSz"])*contract_value
    return {
        "tick_size":float(tick),"lot_size":float(lot),"minimum_order_size":float(minimum),
        "contract_value":float(contract_value),"price_precision":max(0,-tick.normalize().as_tuple().exponent),
        "quantity_precision":max(0,-lot.normalize().as_tuple().exponent),
        "instrument_family":item.get("instFamily"),"fee_group_id":item.get("groupId"),"state":item.get("state"),
    }

def attached_exit_orders(local_id,contracts,lot_contracts,tick_size,take_profit_prices,
                         target_allocations,stop_loss_price,break_even_rule="OFF"):
    """Build OKX attached exits, including split TPs and one SL for the remainder."""
    targets=list(take_profit_prices or [])
    if len(targets)>10:raise ValueError("OKX supports at most 10 split take-profit targets")
    root="SMA"+local_id.replace("-","")[:26]
    orders=[];metadata={}
    amendable_stop=break_even_rule in {"ONE_R","AFTER_TARGET"} and stop_loss_price is not None
    if break_even_rule=="AFTER_TARGET" and len(targets)>1:
        targets=[targets[-1]];target_allocations=[1]
    if len(targets)<=1 and not amendable_stop:
        attached={"attachAlgoClOrdId":root+"X"}
        if targets:
            attached.update({"tpTriggerPx":price_to_tick(targets[0],tick_size),
                             "tpTriggerPxType":"last","tpOrdPx":"-1"})
        if stop_loss_price is not None:
            attached.update({"slTriggerPx":price_to_tick(stop_loss_price,tick_size),
                             "slTriggerPxType":"last","slOrdPx":"-1"})
        if len(attached)>1:
            orders.append(attached);metadata[attached["attachAlgoClOrdId"]]={"kind":"PROTECTIVE"}
        return orders,metadata
    if len(targets)==1 and not target_allocations:target_allocations=[1]
    if len(target_allocations)!=len(targets):
        raise ValueError("Split take-profit allocations must match the number of targets")
    allocations=[Decimal(str(value)) for value in target_allocations]
    if any(value<=0 for value in allocations) or abs(sum(allocations)-Decimal("1"))>Decimal("0.000001"):
        raise ValueError("Split take-profit allocations must be positive and sum to one")
    allocated=Decimal("0")
    for index,(target,allocation) in enumerate(zip(targets,allocations)):
        size=(contracts-allocated if index==len(targets)-1 else
              ((contracts*allocation)//lot_contracts)*lot_contracts)
        if size<=0:raise ValueError("Order quantity is too small for the configured split take-profits")
        allocated+=size;algo_id=root+f"T{index}"
        orders.append({"attachAlgoClOrdId":algo_id,"tpTriggerPx":price_to_tick(target,tick_size),
                       "tpTriggerPxType":"last","tpOrdPx":"-1","sz":format(size,"f")})
        metadata[algo_id]={"kind":"TAKE_PROFIT","target_price":float(target)}
    if allocated!=contracts:raise ValueError("Split take-profit sizes do not cover the entry order")
    if stop_loss_price is not None:
        algo_id=root+"S"
        orders.append({"attachAlgoClOrdId":algo_id,"slTriggerPx":price_to_tick(stop_loss_price,tick_size),
                       "slTriggerPxType":"last","slOrdPx":"-1","amendPxOnTriggerType":"0"})
        metadata[algo_id]={"kind":"STOP_LOSS"}
    return orders,metadata

class ExchangeGateway:
    def __init__(self,s):
        self.s=s;self.client=None;self.db=None;self.redis=None;self.tasks=set();self.connected={"public":False,"business":False,"private":False};self.last_error=None
        self.history_semaphore=asyncio.Semaphore(s.history_concurrency);self.running_history=set()
        self.history_request_lock=asyncio.Lock();self.history_request_next=0.0;self.history_request_interval=.12
        self.active_symbols=None;self.websockets={};self.market_page_cache={};self.market_page_locks={};self.private_ready=asyncio.Event();self.pending={}
        self.reconciled=False;self.private_subscribed=False
        self.last_market_message=None;self.last_m1_by_symbol={}
        self.command_task=None
    async def start(self):
        self.client=httpx.AsyncClient(timeout=20)
        self.db=await asyncpg.create_pool(self.s.database_url,min_size=1,max_size=5)
        self.redis=Redis.from_url(self.s.redis_url,decode_responses=True);await self.redis.ping()
        await self.db.execute("""
          CREATE TABLE IF NOT EXISTS exchange_history_jobs(
            id uuid PRIMARY KEY,status text NOT NULL,symbol text NOT NULL,timeframes jsonb NOT NULL,
            from_timestamp bigint,to_timestamp bigint,max_candles integer NOT NULL,cursors jsonb NOT NULL DEFAULT '{}',
            timeframe_counts jsonb NOT NULL DEFAULT '{}',ingested integer NOT NULL DEFAULT 0,
            requests integer NOT NULL DEFAULT 0,progress smallint NOT NULL DEFAULT 0,error text,
            created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now()
          )
        """)
        await self.db.execute("ALTER TABLE exchange_history_jobs ADD COLUMN IF NOT EXISTS timeframe_status jsonb NOT NULL DEFAULT '{}'")
        await self.db.execute("ALTER TABLE exchange_history_jobs ADD COLUMN IF NOT EXISTS timeframe_from jsonb NOT NULL DEFAULT '{}'")
        await self.db.execute("ALTER TABLE exchange_history_jobs ADD COLUMN IF NOT EXISTS mode text NOT NULL DEFAULT 'FULL'")
        await self.db.execute("ALTER TABLE exchange_history_jobs ADD COLUMN IF NOT EXISTS timeframe_to jsonb NOT NULL DEFAULT '{}'")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS tick_size double precision")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS lot_size double precision")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS contract_value double precision NOT NULL DEFAULT 1")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS maker_fee_rate double precision")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS taker_fee_rate double precision")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS funding_rate double precision")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS next_funding_time bigint")
        await self.db.execute("ALTER TABLE trading_assets ADD COLUMN IF NOT EXISTS exchange_metadata jsonb NOT NULL DEFAULT '{}'")
        await self.db.execute("""CREATE TABLE IF NOT EXISTS exchange_orders(
          local_order_id uuid PRIMARY KEY,cl_ord_id text UNIQUE NOT NULL,exchange_order_id text,symbol text NOT NULL,
          status text NOT NULL,payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())""")
        await self.db.execute("""CREATE TABLE IF NOT EXISTS trading_configs(symbol text PRIMARY KEY,mode text NOT NULL DEFAULT 'PAPER',
          status text NOT NULL DEFAULT 'ACTIVE',config jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now())""")
        await self.db.execute("ALTER TABLE trading_configs ADD COLUMN IF NOT EXISTS owner_id text")
        await self.db.execute("""CREATE TABLE IF NOT EXISTS orders(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,
          status text NOT NULL,data jsonb NOT NULL,created_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now())""")
        await self.db.execute("""CREATE TABLE IF NOT EXISTS positions(id uuid PRIMARY KEY,signal_id uuid,symbol text NOT NULL,
          status text NOT NULL,data jsonb NOT NULL,opened_at timestamptz NOT NULL,updated_at timestamptz NOT NULL DEFAULT now())""")
        await self.db.execute("ALTER TABLE exchange_orders ADD COLUMN IF NOT EXISTS exit_algo_cl_ord_id text")
        await self.db.execute("ALTER TABLE exchange_orders ADD COLUMN IF NOT EXISTS exit_algos jsonb NOT NULL DEFAULT '{}'")
        await self.db.execute("CREATE UNIQUE INDEX IF NOT EXISTS exchange_orders_exit_algo_idx ON exchange_orders(exit_algo_cl_ord_id) WHERE exit_algo_cl_ord_id IS NOT NULL")
        await self.db.execute("""CREATE TABLE IF NOT EXISTS live_trading_logs(
          id bigserial PRIMARY KEY,local_order_id uuid,symbol text NOT NULL,execution_mode text NOT NULL,
          event_type text NOT NULL,status text NOT NULL,details jsonb NOT NULL DEFAULT '{}',
          created_at timestamptz NOT NULL DEFAULT now())""")
        await self.db.execute("CREATE INDEX IF NOT EXISTS live_trading_logs_created_idx ON live_trading_logs(created_at DESC)")
        await self.db.execute("CREATE INDEX IF NOT EXISTS live_trading_logs_order_idx ON live_trading_logs(local_order_id,created_at)")
        await self.db.execute("UPDATE exchange_history_jobs SET status='QUEUED' WHERE status='RUNNING'")
        await self.db.execute("""UPDATE exchange_history_jobs SET timeframe_status=(
          SELECT coalesce(jsonb_object_agg(key,CASE WHEN value->>'status'='RUNNING'
            THEN jsonb_set(value,'{status}','\"QUEUED\"') ELSE value END),'{}'::jsonb)
          FROM jsonb_each(timeframe_status)) WHERE timeframe_status<>'{}'::jsonb""")
        await self.refresh_symbols()
        for row in await self.db.fetch("SELECT id FROM exchange_history_jobs WHERE status='QUEUED'"):
            self.schedule_history(row["id"])
        if self.s.market_data_enabled:
            self.add_task(self.loop("public",self.s.okx_public_ws_url));self.add_task(self.loop("business",self.s.okx_business_ws_url))
            self.add_task(self.watch_trading_configs())
            self.add_task(self.sync_active_history())
        if self.s.trading_enabled:
            if not all((self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)):
                self.last_error="Private trading enabled but OKX credentials are not configured"
            else:
                self.add_task(self.private_loop());self.command_task=self.add_task(self.consume_orders())
                self.add_task(self.reconcile_loop())
    async def stop(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        if self.client:await self.client.aclose()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    def add_task(self,coroutine):
        task=asyncio.create_task(coroutine);self.tasks.add(task);task.add_done_callback(self.tasks.discard);return task
    @property
    def symbols(self):return self.active_symbols if self.active_symbols is not None else [x.strip().upper() for x in self.s.symbols.split(",") if x.strip()]
    @property
    def timeframes(self):return sorted(getattr(self,"active_timeframes",set()) | {"M1"} | {x.strip().upper() for x in self.s.timeframes.split(",") if x.strip().upper() in TIMEFRAMES})
    @property
    def market_data_ready(self):
        return all(self.market_data_ready_for(symbol) for symbol in self.symbols)
    def market_data_ready_for(self,symbol):
        seen=self.last_m1_by_symbol.get(symbol)
        return self.connected["business"] and seen is not None and monotonic()-seen<120
    @property
    def trading_ready(self):
        return self.private_ready.is_set() and self.reconciled and (self.command_task is None or not self.command_task.done())
    async def loop(self,name,url):
        delay=1
        while True:
            try:
                async with websockets.connect(url,ping_interval=20,ping_timeout=10,max_size=2**22) as ws:
                    self.websockets[name]=ws
                    if name=="business":
                        self.last_market_message=None;self.last_m1_by_symbol.clear()
                    self.connected[name]=True;delay=1
                    args=[]
                    if name=="public":args=[{"channel":c,"instId":s} for s in self.symbols for c in ("trades","books5")]
                    else:args=[{"channel":"candle"+TIMEFRAMES[t],"instId":s} for s in self.symbols for t in self.timeframes]
                    await ws.send(json.dumps({"op":"subscribe","args":args}))
                    async for raw in ws:await self.handle(json.loads(raw))
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.last_error=f"{name}: {type(exc).__name__}: {exc}"[:500]
                self.connected[name]=False;await asyncio.sleep(delay+random.random());delay=min(delay*2,60)  # nosec B311
            finally:self.websockets.pop(name,None)
    async def refresh_symbols(self,refresh_metadata=True):
        previous_symbols=self.active_symbols
        previous_timeframes=getattr(self,"active_timeframes",set())
        try:rows=await self.db.fetch("""SELECT ta.symbol FROM trading_assets ta JOIN trading_configs tc ON tc.symbol=ta.symbol
          WHERE ta.enabled AND ta.validation_status='ACTIVE' AND tc.status='ACTIVE' ORDER BY ta.symbol""")
        except asyncpg.UndefinedTableError:rows=[]
        self.active_symbols=[row["symbol"] for row in rows]
        try:
            configs=await self.db.fetch("SELECT config FROM trading_configs WHERE status='ACTIVE'")
            self.active_timeframes=set()
            for row in configs:
                config=row["config"] if isinstance(row["config"],dict) else json.loads(row["config"])
                elliott=config.get("elliott") or {}
                for key in ("entryTimeframe","structureTimeframe","macroTimeframe","entry_timeframe","structure_timeframe","macro_timeframe"):
                    value=elliott.get(key)
                    if value in TIMEFRAMES:self.active_timeframes.add(value)
        except asyncpg.UndefinedTableError:self.active_timeframes=set()
        if refresh_metadata:await self.refresh_instrument_specs(self.active_symbols)
        if previous_symbols!=self.active_symbols or previous_timeframes!=self.active_timeframes:
            for name,connection in list(self.websockets.items()):
                if name!="private":await connection.close()
        return self.symbols
    async def watch_trading_configs(self):
        while True:
            pubsub=self.redis.pubsub()
            try:
                await pubsub.subscribe("trading.config")
                async for message in pubsub.listen():
                    if message["type"]!="message":continue
                    event=json.loads(message["data"])
                    if event.get("event_type")=="trading.config.deleted":
                        symbol=(event.get("payload") or {}).get("symbol")
                        if symbol:
                            await self.db.execute("""UPDATE exchange_history_jobs SET status='CANCELLED',updated_at=now()
                              WHERE symbol=$1 AND mode='AUTO' AND status IN ('QUEUED','RUNNING')""",symbol)
                    await self.refresh_symbols()
                    await self.ensure_active_history(audit_gaps=True)
            except asyncio.CancelledError:raise
            except Exception:
                log.exception("Trading configuration listener failed")
                await asyncio.sleep(2)
            finally:await pubsub.aclose()
    async def sync_active_history(self):
        iteration=0
        while True:
            try:
                await self.refresh_symbols(refresh_metadata=iteration%240==0)
                await self.ensure_active_history(audit_gaps=iteration%40==0)
            except asyncio.CancelledError:raise
            except Exception:log.exception("Active trading history sync failed")
            iteration+=1
            await asyncio.sleep(15)
    async def ensure_active_history(self,audit_gaps=False):
        configs=await self.db.fetch("SELECT symbol,config FROM trading_configs WHERE status='ACTIVE'")
        for row in configs:
            symbol=row["symbol"]
            config=row["config"] if isinstance(row["config"],dict) else json.loads(row["config"])
            elliott=config.get("elliott") or {}
            required={"M1"}
            for key in ("entryTimeframe","structureTimeframe","macroTimeframe"):
                required.add(elliott.get(key) or {"entryTimeframe":"M15","structureTimeframe":"H1","macroTimeframe":"H4"}[key])
            if not required <= TIMEFRAMES.keys():
                self.last_error=f"Unsupported active timeframe for {symbol}"
                continue
            running=await self.db.fetchval("SELECT EXISTS(SELECT 1 FROM exchange_history_jobs WHERE symbol=$1 AND status IN ('QUEUED','RUNNING'))",symbol)
            if running:continue
            found=await self.db.fetch("""SELECT timeframe,count(*) AS count,
              (extract(epoch from max(ts))*1000)::bigint AS latest
              FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[]) AND is_closed GROUP BY timeframe""",symbol,list(required))
            counts={item["timeframe"]:item["count"] for item in found}
            missing=[tf for tf in sorted(required) if counts.get(tf,0)==0]
            end=int(time()*1000)
            if missing:
                await self.create_history(str(uuid4()),symbol,missing,end-180*86_400_000,end,auto=True)
                continue
            if not audit_gaps:continue
            for timeframe in sorted(required):
                span=TIMEFRAME_MILLISECONDS[timeframe]
                gap=await self.db.fetchrow("""SELECT previous,(extract(epoch from ts)*1000)::bigint AS current
                  FROM (SELECT ts,(extract(epoch from lag(ts) OVER (ORDER BY ts))*1000)::bigint AS previous
                        FROM (SELECT ts FROM candles WHERE symbol=$1 AND timeframe=$2 AND is_closed
                              ORDER BY ts DESC LIMIT 1000) recent) gaps
                  WHERE previous IS NOT NULL AND (extract(epoch from ts)*1000)::bigint-previous>$3
                  ORDER BY ts DESC LIMIT 1""",symbol,timeframe,span)
                if gap:
                    await self.create_history(str(uuid4()),symbol,[timeframe],gap["previous"]+span,
                                              gap["current"]-span,auto=True)
                    break
                latest=next((item["latest"] for item in found if item["timeframe"]==timeframe),None)
                if latest is not None and end-latest>max(2*span,300_000):
                    await self.create_history(str(uuid4()),symbol,[timeframe],latest+span,end,
                                              incremental=True,auto=True)
                    break
    async def refresh_instrument_specs(self,symbols):
        refreshed=[]
        for symbol in symbols:
            try:
                response=await self.client.get(
                    self.s.okx_rest_url+"/api/v5/public/instruments",params={"instType":"SWAP","instId":symbol},
                )
                response.raise_for_status();body=response.json();items=body.get("data") or []
                if body.get("code")!="0" or not items:continue
                instrument=items[0];spec=instrument_spec(instrument)
                funding={}
                try:
                    funding_response=await self.client.get(self.s.okx_rest_url+"/api/v5/public/funding-rate",params={"instId":symbol})
                    funding_response.raise_for_status();funding_body=funding_response.json()
                    if funding_body.get("code")=="0":funding=(funding_body.get("data") or [{}])[0]
                except Exception as exc:self.last_error=f"funding metadata {symbol}: {type(exc).__name__}: {exc}"[:500]
                maker=taker=None
                if all((self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)) and spec["fee_group_id"]:
                    try:
                        fees=await self.private("GET",f"/api/v5/account/trade-fee?instType=SWAP&groupId={spec['fee_group_id']}")
                        groups=(fees[0].get("feeGroup") if fees else []) or []
                        group=next((item for item in groups if item.get("groupId")==spec["fee_group_id"]),None)
                        if group:maker=float(group["maker"]);taker=float(group["taker"])
                    except Exception as exc:self.last_error=f"fee metadata {symbol}: {type(exc).__name__}: {exc}"[:500]
                await self.db.execute(
                    """UPDATE trading_assets SET tick_size=$2,lot_size=$3,minimum_order_size=$4,
                       price_precision=$5,quantity_precision=$6,contract_value=$7,validation_status='ACTIVE',updated_at=now()
                       ,maker_fee_rate=$8,taker_fee_rate=$9,funding_rate=$10,next_funding_time=$11,exchange_metadata=$12::jsonb
                       WHERE symbol=$1""",
                    symbol,spec["tick_size"],spec["lot_size"],spec["minimum_order_size"],spec["price_precision"],
                    spec["quantity_precision"],spec["contract_value"],maker,taker,float(funding.get("fundingRate") or 0),
                    int(funding.get("nextFundingTime") or 0),json.dumps({"source":"OKX","instrument":instrument,"funding":funding}),
                )
                refreshed.append(symbol)
            except Exception as exc:
                self.last_error=f"instrument metadata {symbol}: {type(exc).__name__}: {exc}"[:500]
        return refreshed
    async def prepare_instruments(self,symbols):
        symbols=list(dict.fromkeys(symbol.strip().upper() for symbol in symbols))
        try:
            response=await self.client.get(
                self.s.okx_rest_url+"/api/v5/public/instruments",params={"instType":"SWAP"})
            response.raise_for_status();body=response.json()
        except (httpx.HTTPError,ValueError) as exc:
            detail=str(exc).strip() or type(exc).__name__
            raise ValueError(f"Unable to load OKX SWAP instruments: {detail}") from exc
        if body.get("code")!="0":
            raise ValueError(f"Unable to load OKX SWAP instruments: OKX {body.get('code')}: {body.get('msg') or 'unknown error'}")
        requested=set(symbols)
        instruments={item.get("instId"):item for item in body.get("data") or [] if item.get("instId") in requested}
        metadata=[]
        for symbol in symbols:
            instrument=instruments.get(symbol)
            if not instrument:continue
            try:spec=instrument_spec(instrument)
            except (KeyError,ValueError,ArithmeticError):continue
            if spec.get("state") not in {None,"live"}:continue
            metadata.append((
                symbol,instrument.get("uly") or symbol,spec["price_precision"],spec["quantity_precision"],
                spec["minimum_order_size"],spec["tick_size"],spec["lot_size"],spec["contract_value"],
                json.dumps({"source":"OKX","instrument":instrument}),
            ))
        if metadata:
            await self.db.executemany(
                """INSERT INTO trading_assets(symbol,display_name,category,enabled,price_precision,quantity_precision,
                     minimum_order_size,tick_size,lot_size,contract_value,validation_status,exchange_metadata)
                   VALUES($1,$2,'crypto',true,$3,$4,$5,$6,$7,$8,'ACTIVE',$9::jsonb)
                   ON CONFLICT(symbol) DO UPDATE SET display_name=excluded.display_name,enabled=true,
                     price_precision=excluded.price_precision,quantity_precision=excluded.quantity_precision,
                     minimum_order_size=excluded.minimum_order_size,tick_size=excluded.tick_size,
                     lot_size=excluded.lot_size,contract_value=excluded.contract_value,
                     validation_status='ACTIVE',exchange_metadata=excluded.exchange_metadata,updated_at=now()""",
                metadata,
            )
        prepared={item[0] for item in metadata}
        await self.refresh_instrument_specs(sorted(prepared))
        active_rows=await self.db.fetch(
            "SELECT symbol FROM trading_assets WHERE enabled AND validation_status='ACTIVE' ORDER BY symbol"
        )
        self.active_symbols=[row["symbol"] for row in active_rows]
        for name,connection in list(self.websockets.items()):
            if name!="private":await connection.close()
        return {"prepared":[symbol for symbol in symbols if symbol in prepared],
                "unavailable":[symbol for symbol in symbols if symbol not in prepared]}
    async def ingest(self,path,payload):
        response=await self.client.post(self.s.data_service_url+path,json=payload,headers={"X-Correlation-ID":"okx-"+str(payload.get("timestamp",0))})
        if response.is_error:raise ValueError(f"{path}: {response.status_code} {response.text[:300]} payload={payload}")
    async def ingest_batch(self,values):
        if not values:return
        response=await self.client.post(
            self.s.data_service_url+"/internal/ingest/candles/batch",json=values,
            headers={"X-Correlation-ID":"okx-history-"+str(values[-1]["timestamp"])},
        );response.raise_for_status()
    async def handle(self,msg):
        if not msg.get("data"):return
        arg=msg.get("arg",{});channel=arg.get("channel","");symbol=arg.get("instId")
        for item in msg["data"]:
            if channel.startswith("candle"):
                timeframe=REVERSE_TIMEFRAMES[channel[6:]]
                await self.ingest("/internal/ingest/candles",candle(item,symbol,timeframe))
                self.last_market_message=monotonic()
                if timeframe=="M1":self.last_m1_by_symbol[symbol]=self.last_market_message
            elif channel=="trades":await self.ingest("/internal/ingest/ticks",trade(item))
            elif channel=="books5":await self.ingest("/internal/ingest/orderbook",book(item,symbol))
    async def private_loop(self):
        delay=1
        while True:
            try:
                async with websockets.connect(self.s.okx_private_ws_url,ping_interval=20,ping_timeout=10,max_size=2**22) as ws:
                    self.websockets["private"]=ws;self.connected["private"]=False
                    await ws.send(json.dumps(ws_login(self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)))
                    async for raw in ws:
                        msg=json.loads(raw)
                        if msg.get("event")=="login" and msg.get("code")=="0":
                            await ws.send(json.dumps({"op":"subscribe","args":[{"channel":"orders","instType":"ANY"}]}));continue
                        if msg.get("event")=="subscribe" and msg.get("arg",{}).get("channel")=="orders" and msg.get("code") in (None,"0"):
                            self.private_subscribed=True;self.connected["private"]=True
                            try:
                                await self.reconcile_orders()
                                self.private_ready.set();delay=1
                            except Exception as exc:
                                self.last_error=f"initial reconciliation: {type(exc).__name__}: {exc}"[:500]
                                log.exception("OKX initial reconciliation failed")
                            continue
                        if msg.get("event") in {"error","login","subscribe"}:
                            raise ValueError(f"OKX private channel rejected: {msg.get('msg') or msg.get('code')}")
                        await self.handle_private(msg)
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.last_error=f"private: {type(exc).__name__}: {exc}"[:500]
            finally:
                self.private_ready.clear();self.reconciled=False;self.private_subscribed=False
                self.connected["private"]=False;self.websockets.pop("private",None)
            await asyncio.sleep(delay+random.random());delay=min(delay*2,60)  # nosec B311
    async def reconcile_orders(self):
        """Recover owned orders after a private-channel gap before accepting entries."""
        self.private_ready.clear();self.reconciled=False
        rows=await self.db.fetch("""SELECT local_order_id,cl_ord_id,symbol FROM exchange_orders
          WHERE status IN ('SUBMITTING','UNKNOWN','ACCEPTED','OPEN','PARTIALLY_FILLED','CANCEL_REQUESTED')""")
        mapping={"LIVE":"OPEN","PARTIALLY_FILLED":"PARTIALLY_FILLED","FILLED":"FILLED",
                 "CANCELED":"CANCELLED","MMP_CANCELED":"CANCELLED"}
        for row in rows:
            path="/api/v5/trade/order?"+urlencode({"instId":row["symbol"],"clOrdId":row["cl_ord_id"]})
            try:items=await self.private("GET",path)
            except ValueError as exc:
                self.last_error=f"reconcile {row['cl_ord_id']}: {exc}"[:500]
                raise
            if not items:
                raise ValueError(f"OKX order {row['cl_ord_id']} has an unresolved exchange state")
            item=items[0];status=mapping.get(str(item.get("state","")).upper(),"UNKNOWN")
            await self.db.execute("UPDATE exchange_orders SET exchange_order_id=$2,status=$3,updated_at=now() WHERE local_order_id=$1::uuid",
                                  row["local_order_id"],item.get("ordId"),status)
            contract=await self.db.fetchval("SELECT coalesce(contract_value,1) FROM trading_assets WHERE symbol=$1",row["symbol"])
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{
                "order_id":str(row["local_order_id"]),"exchange_order_id":item.get("ordId"),"status":status,
                "filled_price":float(item.get("avgPx") or 0),
                "filled_quantity":float(item.get("accFillSz") or 0)*float(contract or 1),"reconciled":True,
                "unprotected_partial":status=="PARTIALLY_FILLED" or (status=="CANCELLED" and Decimal(str(item.get("accFillSz") or 0))>0)}})},maxlen=100000,approximate=True)
            if status=="PARTIALLY_FILLED":
                try:await self.cancel_order(str(row["local_order_id"]))
                except Exception as exc:self.last_error=f"partial fill cancellation: {exc}"[:500]
                raise ValueError(f"Partial entry {row['cl_ord_id']} requires a forced exit")
        if await self.recover_protective_fills():
            raise ValueError("Recovered OKX protective fills; waiting for local position update")
        positions=await self.private("GET","/api/v5/account/positions?instType=SWAP")
        local_positions=await self.db.fetch("""SELECT symbol,
          sum(CASE WHEN data->>'direction'='SHORT' THEN -(data->>'quantity')::numeric ELSE (data->>'quantity')::numeric END) AS quantity
          FROM positions WHERE status!='CLOSED' GROUP BY symbol""") if await self.db.fetchval("SELECT to_regclass('public.positions') IS NOT NULL") else []
        local_quantities={row["symbol"]:Decimal(str(row["quantity"] or 0)) for row in local_positions}
        exchange_quantities={}
        for item in positions:
            if Decimal(str(item.get("pos") or 0))==0:continue
            contract=await self.db.fetchval("SELECT coalesce(contract_value,1) FROM trading_assets WHERE symbol=$1",item.get("instId"))
            exchange_quantities[item.get("instId")]=exchange_quantities.get(item.get("instId"),Decimal(0))+Decimal(str(item["pos"]))*Decimal(str(contract or 1))
            owned=await self.db.fetchval("""SELECT EXISTS(SELECT 1 FROM positions WHERE symbol=$1 AND status!='CLOSED'
              UNION ALL SELECT 1 FROM exchange_orders WHERE symbol=$1 AND status IN ('SUBMITTING','UNKNOWN','ACCEPTED','OPEN','PARTIALLY_FILLED','FILLED'))""",item.get("instId"))
            if not owned:raise ValueError(f"Unmanaged OKX position on {item.get('instId')}; new entries are blocked")
        for symbol in set(local_quantities) | set(exchange_quantities):
            local=local_quantities.get(symbol,Decimal(0));actual=exchange_quantities.get(symbol,Decimal(0))
            if abs(local-actual)>Decimal("0.00000001"):
                raise ValueError(f"OKX position mismatch on {symbol}: local={local}, exchange={actual}")
        protected=await self.db.fetch("""SELECT p.id,p.symbol,p.data,eo.exit_algos
          FROM positions p LEFT JOIN exchange_orders eo ON eo.local_order_id=(p.data->>'order_id')::uuid
          WHERE p.status!='CLOSED' AND p.data->>'execution_mode' IN ('DEMO','PRODUCTION')""")
        for row in protected:
            position=row["data"] if isinstance(row["data"],dict) else json.loads(row["data"])
            if position.get("force_exit"):continue
            algos=row["exit_algos"] or {}
            if isinstance(algos,str):algos=json.loads(algos)
            stop_id=next((key for key,metadata in algos.items() if metadata.get("kind") in {"STOP_LOSS","PROTECTIVE"}),None)
            if not stop_id:
                await self.report_missing_protection(row["id"],row["symbol"],"No owned stop-loss algo")
                raise ValueError(f"Missing OKX protective stop for {row['symbol']}")
            try:details=await self.private("GET","/api/v5/trade/order-algo?"+urlencode({"algoClOrdId":stop_id}))
            except ExchangeAmbiguousError:raise
            except ValueError as exc:
                await self.report_missing_protection(row["id"],row["symbol"],str(exc))
                raise ValueError(f"Cannot confirm OKX protective stop for {row['symbol']}") from exc
            if not details or str(details[0].get("state","")).lower()!="live":
                await self.report_missing_protection(row["id"],row["symbol"],"Stop-loss algo is not live")
                raise ValueError(f"Inactive OKX protective stop for {row['symbol']}")
        self.reconciled=True
    async def report_missing_protection(self,position_id,symbol,reason):
        await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.protection_missing",
          "payload":{"position_id":str(position_id),"symbol":symbol,"reason":reason}})},maxlen=100000,approximate=True)
    async def recover_protective_fills(self):
        rows=await self.db.fetch("""SELECT p.data,eo.local_order_id,eo.symbol,eo.exit_algos,
          coalesce(ta.contract_value,1) AS contract_value
          FROM positions p JOIN exchange_orders eo ON eo.local_order_id=(p.data->>'order_id')::uuid
          LEFT JOIN trading_assets ta ON ta.symbol=eo.symbol
          WHERE p.status!='CLOSED' AND p.data->>'execution_mode' IN ('DEMO','PRODUCTION')""")
        recovered=False
        for row in rows:
            position=row["data"] if isinstance(row["data"],dict) else json.loads(row["data"])
            algos=row["exit_algos"] or {}
            if isinstance(algos,str):algos=json.loads(algos)
            for algo_id,metadata in algos.items():
                details=await self.private("GET","/api/v5/trade/order-algo?"+urlencode({"algoClOrdId":algo_id}))
                if not details or str(details[0].get("state","")).lower()!="effective":continue
                order_id=details[0].get("ordId")
                if not order_id:raise ValueError(f"Triggered OKX algo {algo_id} has no order ID")
                orders=await self.private("GET","/api/v5/trade/order?"+urlencode({"instId":row["symbol"],"ordId":order_id}))
                if not orders:raise ValueError(f"Triggered OKX order {order_id} is unavailable")
                item=orders[0]
                cumulative=float(item.get("accFillSz") or 0)*float(row["contract_value"])
                processed=float(position.get("protective_filled_quantities",{}).get(algo_id,0))
                if cumulative<=processed+1e-12:continue
                price=float(item.get("avgPx") or 0)
                if price<=0:raise ValueError(f"Triggered OKX order {order_id} has no fill price")
                await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{
                  "order_id":str(row["local_order_id"]),"exchange_order_id":order_id,
                  "status":"FILLED" if item.get("state")=="filled" else "PARTIALLY_FILLED",
                  "filled_price":price,"filled_quantity":cumulative,"position_exit":True,
                  "protective_id":algo_id,"protective_kind":metadata.get("kind"),
                  "target_price":metadata.get("target_price"),"reconciled":True}})},maxlen=100000,approximate=True)
                recovered=True
        return recovered
    async def reconcile_loop(self):
        while True:
            await asyncio.sleep(30)
            if not self.connected["private"]:continue
            try:
                await self.reconcile_orders()
                self.private_ready.set()
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.last_error=f"reconciliation: {type(exc).__name__}: {exc}"[:500]
                log.exception("OKX reconciliation failed")
    async def handle_private(self,msg):
        request_id=msg.get("id")
        if request_id and request_id in self.pending:
            future=self.pending.pop(request_id)
            if not future.done():future.set_result(msg)
        if msg.get("arg",{}).get("channel")!="orders":return
        for item in msg.get("data",[]):
            cl_ord_id=item.get("clOrdId","")
            algo_cl_ord_id=item.get("algoClOrdId","")
            if item.get("tag")!="SMPELLIOTT" and not (cl_ord_id.startswith("SMP") or algo_cl_ord_id.startswith("SMA")):continue
            row=await self.db.fetchrow("""SELECT eo.local_order_id,o.data->>'execution_mode' AS execution_mode,
                coalesce(ta.contract_value,1)::float8 AS contract_value,
                (eo.exit_algo_cl_ord_id=$2 OR coalesce(eo.exit_algos,'{}'::jsonb) ? $2) AS position_exit,
                coalesce(eo.exit_algos,'{}'::jsonb)->$2 AS exit_metadata
              FROM exchange_orders eo LEFT JOIN orders o ON o.id=eo.local_order_id
              LEFT JOIN trading_assets ta ON ta.symbol=eo.symbol
              WHERE eo.cl_ord_id=$1 OR eo.exit_algo_cl_ord_id=$2
                 OR coalesce(eo.exit_algos,'{}'::jsonb) ? $2""",cl_ord_id,algo_cl_ord_id)
            if not row:continue
            state=item.get("state","").upper();mapping={"LIVE":"OPEN","PARTIALLY_FILLED":"PARTIALLY_FILLED","FILLED":"FILLED","CANCELED":"CANCELLED","MMP_CANCELED":"CANCELLED"};status=mapping.get(state,state)
            if not row["position_exit"]:
                await self.db.execute("UPDATE exchange_orders SET exchange_order_id=$2,status=$3,payload=$4::jsonb,updated_at=now() WHERE cl_ord_id=$1",cl_ord_id,item.get("ordId"),status,json.dumps(item))
            await self.record_trading_log({"id":str(row["local_order_id"]),"symbol":item.get("instId","UNKNOWN"),
              "execution_mode":row["execution_mode"] or ("DEMO" if self.s.okx_demo else "PRODUCTION")},
              "ORDER_UPDATE",status,{"exchange_order_id":item.get("ordId"),"exchange":item})
            exit_metadata=(json.loads(row["exit_metadata"]) if isinstance(row["exit_metadata"],str)
                           else row["exit_metadata"] or {})
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{"order_id":str(row["local_order_id"]),"exchange_order_id":item.get("ordId"),"status":status,"filled_price":float(item.get("avgPx") or item.get("fillPx") or 0),"filled_quantity":float(item.get("accFillSz") or 0)*float(row["contract_value"]),"exec_type":item.get("execType"),"raw_state":state,"position_exit":bool(row["position_exit"]),"protective_id":algo_cl_ord_id or None,"protective_kind":exit_metadata.get("kind"),"target_price":exit_metadata.get("target_price"),"unprotected_partial":not row["position_exit"] and (status=="PARTIALLY_FILLED" or status=="CANCELLED" and float(item.get("accFillSz") or 0)>0),"reason":"EXCHANGE_PROTECTIVE_EXIT" if row["position_exit"] else None}})},maxlen=100000,approximate=True)
            if status=="PARTIALLY_FILLED" and not row["position_exit"]:
                self.private_ready.clear();self.reconciled=False
                try:await self.cancel_order(str(row["local_order_id"]))
                except Exception as exc:self.last_error=f"partial fill cancellation: {exc}"[:500]
    async def ws_request(self,op,args,request_id):
        await asyncio.wait_for(self.private_ready.wait(),timeout=15);ws=self.websockets.get("private")
        if not ws:raise ValueError("OKX private WebSocket is unavailable")
        future=asyncio.get_running_loop().create_future();self.pending[request_id]=future
        await ws.send(json.dumps({"id":request_id,"op":op,"expTime":str(int(time()*1000)+10_000),"args":[args]}))
        try:response=await asyncio.wait_for(future,timeout=15)
        finally:self.pending.pop(request_id,None)
        data=(response.get("data") or [{}])[0]
        if response.get("code") not in (None,"0") or data.get("sCode","0")!="0":
            details={"code":response.get("code"),"msg":response.get("msg"),
                     "sCode":data.get("sCode"),"sMsg":data.get("sMsg")}
            raise ValueError(f"OKX rejected request: {json.dumps(details,separators=(',',':'))}")
        return data
    async def consume_orders(self):
        group="exchange-gateway"
        try:await self.redis.xgroup_create("execution.command",group,id="0",mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):raise
        while True:
            try:
                batches=await self.redis.xreadgroup(group,"exchange-1",{"execution.command":"0"},count=10)
                if not batches or not batches[0][1]:
                    claimed=await self.redis.xautoclaim("execution.command",group,"exchange-1",60000,start_id="0-0",count=10)
                    batches=[("execution.command",claimed[1])] if claimed[1] else await self.redis.xreadgroup(group,"exchange-1",{"execution.command":">"},count=10,block=2000)
            except asyncio.CancelledError:raise
            except Exception:
                log.exception("Exchange command consumer failed");await asyncio.sleep(2);continue
            for _,messages in batches:
                for message_id,fields in messages:
                    event={}
                    try:
                        event=json.loads(fields["data"]);payload=event.get("payload",{})
                        if event.get("event_type")=="order.request":await self.place_order(payload)
                        elif event.get("event_type")=="order.cancel_requested":await self.cancel_order(payload["order_id"])
                        elif event.get("event_type")=="position.protection_requested":await self.amend_protection(payload)
                        await self.redis.xack("execution.command",group,message_id)
                    except asyncio.CancelledError:raise
                    except Exception as exc:
                        if isinstance(exc,TradingNotReadyError):
                            await asyncio.sleep(2)
                            continue
                        self.last_error=f"order command: {type(exc).__name__}: {exc}"[:500]
                        log.exception("Order command failed: local_order_id=%s",event.get("payload",{}).get("id"))
                        try:await self.handle_command_failure(event,exc,group,message_id)
                        except asyncio.CancelledError:raise
                        except Exception:
                            log.exception("Could not record command failure; command remains pending")
                            await asyncio.sleep(2)
    async def handle_command_failure(self,event,exc,group,message_id):
        payload=event.get("payload") or {}
        if event.get("event_type")=="position.protection_requested":
            await self.record_trading_log(payload,"PROTECTION_REJECTED","REJECTED",{"reason":str(exc)})
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.protection_updated","payload":{
              **payload,"status":"REJECTED","reason":str(exc)}})},maxlen=100000,approximate=True)
        elif payload.get("id"):
            existing=await self.db.fetchrow("SELECT status FROM exchange_orders WHERE local_order_id=$1::uuid",payload["id"])
            uncertain=isinstance(exc,ExchangeAmbiguousError) or (existing and existing["status"] in {
              "SUBMITTING","UNKNOWN","ACCEPTED","OPEN","PARTIALLY_FILLED","FILLED"})
            if uncertain:
                await self.db.execute("UPDATE exchange_orders SET status='UNKNOWN',updated_at=now() WHERE local_order_id=$1::uuid AND status IN ('SUBMITTING','UNKNOWN')",payload["id"])
                status="UNKNOWN"
            else:
                await self.db.execute("""UPDATE exchange_orders SET status='REJECTED',
                  payload=payload||jsonb_build_object('error',$2::text),updated_at=now()
                  WHERE local_order_id=$1::uuid""",payload["id"],str(exc))
                status="REJECTED"
            await self.record_trading_log(payload,"ORDER_"+status,status,{"reason":str(exc)})
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{
              "order_id":payload["id"],"status":status,"reason":str(exc)}})},maxlen=100000,approximate=True)
        await self.redis.xack("execution.command",group,message_id)
    async def instrument_order_spec(self,symbol):
        row=await self.db.fetchrow("SELECT contract_value,lot_size,minimum_order_size,tick_size,validation_status,enabled FROM trading_assets WHERE symbol=$1",symbol)
        if not row or row["validation_status"]!="ACTIVE" or not row["enabled"]:raise ValueError("Exchange instrument is disabled or metadata is unavailable")
        return row
    async def trading_instrument_spec(self,symbol):
        mode="OKX Demo" if self.s.okx_demo else "OKX Production"
        path="/api/v5/account/instruments?"+urlencode({"instType":"SWAP","instId":symbol})
        try:items=await self.private("GET",path)
        except ExchangeAmbiguousError as exc:raise TradingNotReadyError(f"OKX instrument lookup unavailable: {exc}") from exc
        except ValueError as exc:raise ValueError(f"{symbol} is unavailable in {mode}: {exc}") from exc
        if not items:raise ValueError(f"{symbol} is unavailable in {mode}")
        return instrument_spec(items[0])
    async def require_safe_account_config(self):
        rows=await self.private("GET","/api/v5/account/config")
        if not rows:raise ValueError("OKX account configuration is unavailable")
        config=rows[0];permissions={item.strip() for item in str(config.get("perm","")).split(",")}
        if "trade" not in permissions:raise ValueError("OKX API key does not have trade permission")
        if "withdraw" in permissions:raise ValueError("OKX API key must not have withdraw permission")
        if not self.s.okx_demo and not str(config.get("ip","")).strip():
            raise ValueError("Production OKX API key must be restricted to server IP addresses")
        if config.get("posMode")!="net_mode":
            raise ValueError("OKX account must use net position mode")
        return config
    async def account_capacity(self,requested_mode):
        requested=requested_mode.upper();gateway_mode="DEMO" if self.s.okx_demo else "PRODUCTION"
        if requested!=gateway_mode:raise ValueError(f"Portfolio mode {requested} does not match OKX gateway mode {gateway_mode}")
        if not self.s.trading_enabled:raise ValueError("OKX trading is disabled")
        await self.require_safe_account_config()
        balances=await self.private("GET","/api/v5/account/balance?ccy=USDT")
        details=(balances[0].get("details",[]) if balances else []) or []
        usdt=next((item for item in details if item.get("ccy")=="USDT"),None)
        if not usdt:raise ValueError("USDT balance is unavailable on OKX account")
        equity=Decimal(str(usdt.get("eq") or 0));available=Decimal(str(usdt.get("availEq") or usdt.get("availBal") or 0))
        return {"mode":requested,"currency":"USDT","equity":float(equity),"available":float(available)}
    async def instrument_availability(self,symbol,requested_mode):
        requested=requested_mode.upper();gateway_mode="DEMO" if self.s.okx_demo else "PRODUCTION"
        if requested=="PAPER":return {"symbol":symbol,"mode":requested,"available":True,"reason":None}
        if requested not in {"DEMO","PRODUCTION"}:
            return {"symbol":symbol,"mode":requested,"available":False,"reason":"Unsupported execution mode"}
        if requested!=gateway_mode:
            return {"symbol":symbol,"mode":requested,"available":False,
              "reason":f"Asset mode {requested} does not match OKX gateway mode {gateway_mode}"}
        if not self.s.trading_enabled:
            return {"symbol":symbol,"mode":requested,"available":False,"reason":"OKX trading is disabled"}
        if not self.trading_ready:
            return {"symbol":symbol,"mode":requested,"available":False,"reason":"OKX private orders channel is not ready or reconciliation is incomplete"}
        try:
            await self.require_safe_account_config()
            spec=await self.trading_instrument_spec(symbol)
            return {"symbol":symbol,"mode":requested,"available":True,"reason":None,"instrument":spec}
        except ValueError as exc:
            return {"symbol":symbol,"mode":requested,"available":False,"reason":str(exc)}
    async def record_trading_log(self,payload,event_type,status,details=None):
        mode=str(payload.get("execution_mode","")).upper()
        if mode not in {"DEMO","PRODUCTION"}:return
        try:
            await self.db.execute("""INSERT INTO live_trading_logs(
              local_order_id,symbol,execution_mode,event_type,status,details)
              VALUES($1::uuid,$2,$3,$4,$5,$6::jsonb)""",payload.get("id"),payload.get("symbol","UNKNOWN"),
              mode,event_type,status,json.dumps(details or {}))
        except Exception:log.exception("Failed to persist live trading log for order %s",payload.get("id"))
    async def place_order(self,payload):
        await self.record_trading_log(payload,"ORDER_RECEIVED","RECEIVED",{
          "side":payload.get("side"),"type":payload.get("type"),"quantity":payload.get("quantity")})
        requested_mode=str(payload.get("execution_mode","")).upper();gateway_mode="DEMO" if self.s.okx_demo else "PRODUCTION"
        if requested_mode not in {"DEMO","PRODUCTION"}:raise ValueError("Only exchange execution modes can reach OKX")
        if requested_mode!=gateway_mode:raise ValueError(f"Asset mode {requested_mode} does not match OKX gateway mode {gateway_mode}")
        channel_ready=(self.private_subscribed or self.private_ready.is_set()) if payload.get("reduce_only") else self.trading_ready
        if not channel_ready:raise TradingNotReadyError("OKX private orders channel is unavailable")
        if not payload.get("reduce_only") and getattr(self.s,"market_data_enabled",False) and not self.market_data_ready_for(payload["symbol"]):
            raise TradingNotReadyError("OKX market candles are unavailable or stale")
        if payload.get("expires_at") is not None and int(payload["expires_at"])<=int(time()*1000):
            raise ValueError("Order request has expired")
        local_id=payload["id"];cl_ord_id="SMP"+local_id.replace("-","")[:29]
        prior=await self.db.fetchrow("SELECT status,exchange_order_id FROM exchange_orders WHERE local_order_id=$1::uuid",local_id)
        if prior:
            return {"order_id":local_id,"exchange_order_id":prior["exchange_order_id"],"status":prior["status"]}
        if not payload.get("reduce_only"):
            active=await self.db.fetchrow("SELECT mode,config FROM trading_configs WHERE symbol=$1 AND status='ACTIVE'",payload["symbol"])
            if not active or active["mode"]!=requested_mode:
                raise ValueError("Trading configuration was removed or its mode changed")
            config=active["config"] if isinstance(active["config"],dict) else json.loads(active["config"])
            if config.get("portfolioId",config.get("portfolio_id"))!=payload.get("portfolio_id"):
                raise ValueError("Trading portfolio changed before order submission")
            if config.get("activationId",config.get("activation_id")) and config.get("activationId",config.get("activation_id"))!=payload.get("activation_id"):
                raise ValueError("Trading activation changed before order submission")
        try:await self.require_safe_account_config()
        except ExchangeAmbiguousError as exc:raise TradingNotReadyError(f"OKX account preflight unavailable: {exc}") from exc
        # A removed asset can still have an open position on OKX. Its exit must
        # remain possible after trading_assets.enabled becomes false.
        if not payload.get("reduce_only"):
            await self.instrument_order_spec(payload["symbol"])
        spec=await self.trading_instrument_spec(payload["symbol"]);contract=Decimal(str(spec["contract_value"]));base_qty=Decimal(str(payload["quantity"]))
        contracts=base_qty/contract;lot_contracts=Decimal(str(spec["lot_size"]))/contract
        contracts=(contracts//lot_contracts)*lot_contracts
        minimum=Decimal(str(spec["minimum_order_size"]))/contract
        if contracts<minimum:raise ValueError("Order quantity is below OKX minSz")
        leverage=int(payload.get("leverage",1));margin_mode=payload.get("margin_mode") or self.s.margin_mode
        if not payload.get("reduce_only"):
            try:await self.private("POST","/api/v5/account/set-leverage",{"instId":payload["symbol"],"lever":str(leverage),"mgnMode":margin_mode})
            except ExchangeAmbiguousError as exc:raise TradingNotReadyError(f"OKX leverage preflight unavailable: {exc}") from exc
        args={"instId":payload["symbol"],"tdMode":margin_mode,"side":payload["side"].lower(),"ordType":payload["type"].lower(),"sz":format(contracts,"f"),"clOrdId":cl_ord_id,"tag":"SMPELLIOTT"}
        if payload.get("price") is not None and payload["type"]!="MARKET":args["px"]=price_to_tick(payload["price"],spec["tick_size"])
        attached,exit_algos=attached_exit_orders(local_id,contracts,lot_contracts,spec["tick_size"],
          payload.get("take_profit_prices",[]),payload.get("target_allocations",[]),payload.get("stop_loss_price"),
          payload.get("break_even_rule","OFF"))
        if attached:args["attachAlgoOrds"]=attached
        exit_algo_cl_ord_id=next(iter(exit_algos),None) if len(exit_algos)==1 else None
        if payload.get("reduce_only"):args["reduceOnly"]=True
        channel_ready=(self.private_subscribed or self.private_ready.is_set()) if payload.get("reduce_only") else self.trading_ready
        if not channel_ready or (not payload.get("reduce_only") and getattr(self.s,"market_data_enabled",False) and not self.market_data_ready_for(payload["symbol"])):
            raise TradingNotReadyError("OKX trading readiness changed before order submission")
        if payload.get("expires_at") is not None and int(payload["expires_at"])<=int(time()*1000):
            raise ValueError("Order request expired before submission")
        if not payload.get("reduce_only"):
            current=await self.db.fetchrow("SELECT mode,config FROM trading_configs WHERE symbol=$1 AND status='ACTIVE'",payload["symbol"])
            if not current or current["mode"]!=requested_mode:raise ValueError("Trading configuration was removed before submission")
            current_config=current["config"] if isinstance(current["config"],dict) else json.loads(current["config"])
            if current_config.get("portfolioId",current_config.get("portfolio_id"))!=payload.get("portfolio_id"):
                raise ValueError("Trading portfolio changed before submission")
            if current_config.get("activationId",current_config.get("activation_id")) and current_config.get("activationId",current_config.get("activation_id"))!=payload.get("activation_id"):
                raise ValueError("Trading activation changed before submission")
        claimed=await self.db.fetchrow("""INSERT INTO exchange_orders(local_order_id,cl_ord_id,symbol,status,payload,exit_algo_cl_ord_id,exit_algos)
          VALUES($1::uuid,$2,$3,'SUBMITTING',$4::jsonb,$5,$6::jsonb)
          ON CONFLICT(local_order_id) DO NOTHING RETURNING local_order_id""",
          local_id,cl_ord_id,payload["symbol"],json.dumps(args),exit_algo_cl_ord_id,json.dumps(exit_algos))
        if not claimed:
            prior=await self.db.fetchrow("SELECT status,exchange_order_id FROM exchange_orders WHERE local_order_id=$1::uuid",local_id)
            if not prior:raise TradingNotReadyError("Order claim is unresolved")
            return {"order_id":local_id,"exchange_order_id":prior["exchange_order_id"],"status":prior["status"]}
        await self.record_trading_log(payload,"ORDER_SUBMITTING","SUBMITTING",{"request":args})
        try:ack=okx_ack(await self.private("POST","/api/v5/trade/order",args),"order")
        except ExchangeAmbiguousError:
            await self.db.execute("UPDATE exchange_orders SET status='UNKNOWN',updated_at=now() WHERE local_order_id=$1::uuid",local_id)
            raise
        except ValueError:
            await self.db.execute("UPDATE exchange_orders SET status='REJECTED',updated_at=now() WHERE local_order_id=$1::uuid",local_id)
            raise
        await self.db.execute("UPDATE exchange_orders SET exchange_order_id=$2,status='ACCEPTED',updated_at=now() WHERE local_order_id=$1::uuid",local_id,ack.get("ordId"))
        await self.record_trading_log(payload,"ORDER_ACCEPTED","ACCEPTED",{"exchange":ack})
        await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{"order_id":local_id,"exchange_order_id":ack.get("ordId"),"status":"OPEN"}})},maxlen=100000,approximate=True)
        return {"order_id":local_id,"exchange_order_id":ack.get("ordId"),"status":"ACCEPTED"}
    async def amend_protection(self,payload):
        row=await self.db.fetchrow("""SELECT eo.symbol,eo.exit_algos,o.data->>'execution_mode' AS execution_mode
          FROM exchange_orders eo LEFT JOIN orders o ON o.id=eo.local_order_id
          WHERE eo.local_order_id=$1::uuid""",payload["order_id"])
        if not row:raise ValueError("Entry order is not owned by this system")
        exit_algos=json.loads(row["exit_algos"]) if isinstance(row["exit_algos"],str) else dict(row["exit_algos"] or {})
        stop_id=next((key for key,value in exit_algos.items() if value.get("kind")=="STOP_LOSS"),None)
        if not stop_id:raise ValueError("Protective stop order is unavailable")
        # Break-even updates may race with asset removal. The exchange spec is
        # still needed to round the stop even while new entries are disabled.
        spec=await self.trading_instrument_spec(row["symbol"])
        stop=price_to_tick(payload["stop_loss_price"],spec["tick_size"])
        request={"instId":row["symbol"],"algoClOrdId":stop_id,"newSlTriggerPx":stop,
                 "newSlOrdPx":"-1","newSlTriggerPxType":"last","reqId":("BE"+payload["order_id"].replace("-","")[:30])[:32]}
        ack=okx_ack(await self.private("POST","/api/v5/trade/amend-algos",request),"protection amendment")
        exit_algos[stop_id]["stop_loss_price"]=float(payload["stop_loss_price"])
        await self.db.execute("UPDATE exchange_orders SET exit_algos=$2::jsonb,updated_at=now() WHERE local_order_id=$1::uuid",
                              payload["order_id"],json.dumps(exit_algos))
        await self.record_trading_log(payload,"PROTECTION_UPDATED","UPDATED",{"exchange":ack,"request":request})
        await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.protection_updated","payload":{
          **payload,"status":"UPDATED"}})},maxlen=100000,approximate=True)
        return {"order_id":payload["order_id"],"status":"UPDATED","stop_loss_price":float(payload["stop_loss_price"])}
    async def cancel_order(self,local_order_id):
        row=await self.db.fetchrow("""SELECT eo.cl_ord_id,eo.symbol,eo.status,o.data->>'execution_mode' AS execution_mode
          FROM exchange_orders eo LEFT JOIN orders o ON o.id=eo.local_order_id WHERE eo.local_order_id=$1::uuid""",local_order_id)
        if not row:
            order=await self.db.fetchrow("SELECT symbol,data->>'execution_mode' AS execution_mode FROM orders WHERE id=$1::uuid",local_order_id)
            if not order:raise ValueError("Order is not owned by this system")
            cl_ord_id="SMP"+local_order_id.replace("-","")[:29]
            await self.db.execute("""INSERT INTO exchange_orders(local_order_id,cl_ord_id,symbol,status,payload)
              VALUES($1::uuid,$2,$3,'CANCELLED','{}'::jsonb) ON CONFLICT(local_order_id) DO NOTHING""",
              local_order_id,cl_ord_id,order["symbol"])
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{
              "order_id":local_order_id,"status":"CANCELLED"}})},maxlen=100000,approximate=True)
            return {"order_id":local_order_id,"status":"CANCELLED"}
        if row["status"] in {"FILLED","CANCELLED"}:raise ValueError("Order is already final")
        okx_ack(await self.private("POST","/api/v5/trade/cancel-order",
                                   {"instId":row["symbol"],"clOrdId":row["cl_ord_id"]}),"cancel")
        await self.record_trading_log({"id":local_order_id,"symbol":row["symbol"],
          "execution_mode":row["execution_mode"]},"CANCEL_REQUESTED","CANCEL_REQUESTED")
        return {"order_id":local_order_id,"status":"CANCEL_REQUESTED"}
    async def exchange_orders(self,limit=100):
        rows=await self.db.fetch("SELECT local_order_id,cl_ord_id,exchange_order_id,symbol,status,payload,created_at,updated_at FROM exchange_orders ORDER BY created_at DESC LIMIT $1",limit)
        return [{**dict(row),"local_order_id":str(row["local_order_id"]),"created_at":row["created_at"].isoformat(),"updated_at":row["updated_at"].isoformat()} for row in rows]
    async def instruments(self):
        rows=await self.db.fetch("""SELECT symbol,tick_size,lot_size,minimum_order_size,contract_value,
          maker_fee_rate,taker_fee_rate,funding_rate,next_funding_time,validation_status,updated_at
          FROM trading_assets WHERE enabled ORDER BY symbol""")
        return [{**dict(row),"updated_at":row["updated_at"].isoformat()} for row in rows]
    async def history(self,symbol,timeframe,limit=100):
        params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":min(limit,300)};body=await self.history_candles_request(params)
        values=[candle(x,symbol,timeframe) for x in body["data"]]
        for value in reversed(values):await self.ingest("/internal/ingest/candles",value)
        return len(values)
    async def market_candles(self,symbol,timeframe,limit=300,after=None):
        key=(symbol,timeframe,after,limit);cached=self.market_page_cache.get(key)
        ttl=10 if after is None else 600
        if cached and monotonic()-cached[0]<ttl:return cached[1]
        lock=self.market_page_locks.setdefault(key,asyncio.Lock())
        async with lock:
            cached=self.market_page_cache.get(key)
            if cached and monotonic()-cached[0]<ttl:return cached[1]
            params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":min(limit,300)}
            if after is not None:params["after"]=str(after)
            body=await self.history_candles_request(params)
            values=[candle(item,symbol,timeframe) for item in body.get("data",[])]
            values.sort(key=lambda item:item["timestamp"])
            self.market_page_cache[key]=(monotonic(),values)
            if len(self.market_page_cache)>5000:
                self.market_page_cache={item:value for item,value in self.market_page_cache.items()
                                        if monotonic()-value[0]<600}
                self.market_page_locks={item:value for item,value in self.market_page_locks.items()
                                        if item in self.market_page_cache or value.locked()}
            return values
    async def history_page(self,symbol,timeframe,after=None):
        params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":300}
        if after is not None:params["after"]=str(after)
        body=await self.history_candles_request(params)
        return [candle(item,symbol,timeframe) for item in body["data"]]
    async def history_candles_request(self,params):
        for attempt in range(6):
            async with self.history_request_lock:
                delay=self.history_request_next-monotonic()
                if delay>0:await asyncio.sleep(delay)
                self.history_request_next=monotonic()+self.history_request_interval
            try:
                response=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params)
                response.raise_for_status();body=response.json()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code!=429 or attempt==5:raise
                await asyncio.sleep(min(8,.5*2**attempt));continue
            if body.get("code")=="0":return body
            if body.get("code")!="50011" or attempt==5:
                raise ValueError(f"OKX {body.get('code')}: {body.get('msg') or 'history request failed'}")
            await asyncio.sleep(min(8,.5*2**attempt))
        raise ValueError("OKX history request retry limit exceeded")
    async def create_history(self,job_id,symbol,timeframes,start,end,incremental=False,backfill=False,auto=False):
        statuses={timeframe:{"status":"QUEUED","progress":0,"ingested":0,"requests":0,"error":None} for timeframe in timeframes}
        timeframe_from={}
        timeframe_to={}
        if incremental:
            rows=await self.db.fetch(
                """SELECT timeframe,(extract(epoch FROM max(ts))*1000)::bigint latest
                   FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[]) AND is_closed GROUP BY timeframe""",
                symbol,timeframes,
            )
            latest={row["timeframe"]:row["latest"] for row in rows}
            timeframe_from={timeframe:incremental_start(timeframe,latest.get(timeframe),start)
                            for timeframe in timeframes}
        if backfill:
            rows=await self.db.fetch(
                """SELECT timeframe,(extract(epoch FROM min(ts))*1000)::bigint earliest
                   FROM candles WHERE symbol=$1 AND timeframe=ANY($2::text[]) AND is_closed GROUP BY timeframe""",
                symbol,timeframes,
            )
            earliest={row["timeframe"]:row["earliest"] for row in rows}
            timeframe_to={timeframe:(earliest.get(timeframe)-1 if earliest.get(timeframe) is not None else end)
                          for timeframe in timeframes}
        await self.db.execute(
            """INSERT INTO exchange_history_jobs(id,status,symbol,timeframes,from_timestamp,to_timestamp,max_candles,
                                                  timeframe_status,timeframe_from,mode,timeframe_to)
               VALUES($1::uuid,'QUEUED',$2,$3::jsonb,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10::jsonb)""",
            job_id,symbol,json.dumps(timeframes),start,end,0,json.dumps(statuses),json.dumps(timeframe_from),
            "AUTO" if auto else ("BACKFILL" if backfill else ("INCREMENTAL" if incremental else "FULL")), json.dumps(timeframe_to),
        )
        self.schedule_history(job_id)
        job=await self.history_job(job_id);await self.publish_history(job);return job
    def schedule_history(self,job_id):
        key=str(job_id)
        if key in self.running_history:return
        self.running_history.add(key);task=self.add_task(self.download_history(job_id))
        task.add_done_callback(lambda _:self.running_history.discard(key))
    async def history_job(self,job_id):
        row=await self.db.fetchrow("SELECT * FROM exchange_history_jobs WHERE id=$1::uuid",job_id)
        if not row:return None
        item=dict(row)
        for field in ("timeframes","cursors","timeframe_counts","timeframe_status","timeframe_from","timeframe_to"):
            if isinstance(item[field],str):item[field]=json.loads(item[field])
        item["id"]=str(item["id"]);item["from"]=item.pop("from_timestamp");item["to"]=item.pop("to_timestamp")
        item["created_at"]=item["created_at"].isoformat();item["updated_at"]=item["updated_at"].isoformat()
        return item
    async def history_jobs(self,limit=50):
        rows=await self.db.fetch("SELECT id FROM exchange_history_jobs ORDER BY created_at DESC LIMIT $1",limit)
        return [await self.history_job(row["id"]) for row in rows]
    async def control_history(self,job_id,action):
        transitions={"pause":("PAUSED",{"QUEUED","RUNNING"}),"cancel":("CANCELLED",{"QUEUED","RUNNING","PAUSED"}),"resume":("QUEUED",{"PAUSED","FAILED"})}
        target,allowed=transitions[action];current=await self.db.fetchval("SELECT status FROM exchange_history_jobs WHERE id=$1::uuid",job_id)
        if current not in allowed:return None
        job=await self.history_job(job_id);statuses=job["timeframe_status"]
        for item in statuses.values():
            if item["status"]!="COMPLETED":item["status"]="QUEUED" if action=="resume" else target
            if action=="resume":item["error"]=None
        await self.db.execute("UPDATE exchange_history_jobs SET status=$2,error=NULL,timeframe_status=$3::jsonb,updated_at=now() WHERE id=$1::uuid",job_id,target,json.dumps(statuses))
        if action=="resume":self.schedule_history(job_id)
        changed=await self.history_job(job_id);await self.publish_history(changed);return changed
    async def download_history(self,job_id):
        async with self.history_semaphore:
            await self.db.execute("UPDATE exchange_history_jobs SET status='RUNNING',updated_at=now() WHERE id=$1::uuid AND status='QUEUED'",job_id)
            try:
                job=await self.history_job(job_id)
                await asyncio.gather(*(self.download_timeframe(job_id,job,timeframe) for timeframe in job["timeframes"]))
                status=await self.db.fetchval("SELECT status FROM exchange_history_jobs WHERE id=$1::uuid",job_id)
                if status in {"PAUSED","CANCELLED"}:return
                current=await self.history_job(job_id)
                failed={key:value for key,value in current["timeframe_status"].items() if value["status"]=="FAILED"}
                if failed:
                    error="; ".join(f"{key}: {value['error']}" for key,value in failed.items())
                    await self.db.execute("UPDATE exchange_history_jobs SET status='FAILED',error=$2,updated_at=now() WHERE id=$1::uuid",job_id,error[:2000])
                    await self.publish_history(await self.history_job(job_id));return
                await self.db.execute("UPDATE exchange_history_jobs SET status='COMPLETED',progress=100,updated_at=now() WHERE id=$1::uuid",job_id)
                await self.publish_history(await self.history_job(job_id))
                self.add_task(self.rebuild_elliott(job["symbol"],job["timeframes"]))
            except asyncio.CancelledError:raise
            except Exception as exc:
                await self.db.execute("UPDATE exchange_history_jobs SET status='FAILED',error=$2,updated_at=now() WHERE id=$1::uuid",job_id,str(exc)[:2000])
                await self.publish_history(await self.history_job(job_id))
    async def download_timeframe(self,job_id,job,timeframe):
        details=job["timeframe_status"].get(timeframe,{"status":"QUEUED","progress":0,"ingested":0,"requests":0,"error":None})
        if details["status"]=="COMPLETED":return
        details["status"]="RUNNING";details["error"]=None
        await self.update_timeframe(job_id,timeframe,details)
        count=int(job["timeframe_counts"].get(timeframe,details["ingested"]));cursor=job["cursors"].get(timeframe,job["to"])
        lower_bound=job.get("timeframe_from",{}).get(timeframe,job["from"])
        upper_bound=job.get("timeframe_to",{}).get(timeframe,job["to"])
        try:
            if lower_bound is not None and job["to"] is not None and lower_bound>job["to"]:
                details["status"]="COMPLETED";await self.update_timeframe(job_id,timeframe,details);return
            while True:
                status=await self.db.fetchval("SELECT status FROM exchange_history_jobs WHERE id=$1::uuid",job_id)
                if status in {"PAUSED","CANCELLED"}:
                    details["status"]=status;await self.update_timeframe(job_id,timeframe,details);return
                page=await self.history_page(job["symbol"],timeframe,cursor)
                if not page:break
                eligible=[item for item in page if item["is_closed"]
                          and (lower_bound is None or item["timestamp"]>=lower_bound)
                          and (upper_bound is None or item["timestamp"]<=upper_bound)]
                await self.ingest_batch(list(reversed(eligible)))
                added=len(eligible);count+=added;details["ingested"]+=added;details["requests"]+=1
                oldest=min(item["timestamp"] for item in page)
                if cursor is not None and oldest>=int(cursor):
                    raise ValueError(f"OKX history pagination stalled at {oldest}")
                cursor=oldest
                progress_from=lower_bound if lower_bound is not None else job["from"]
                progress_to=upper_bound if upper_bound is not None else job["to"]
                if progress_from is not None and progress_to is not None:
                    span=max(1,int(progress_to)-int(progress_from))
                    details["progress"]=min(99,max(1,int((int(progress_to)-oldest)/span*100)))
                await self.db.execute(
                    """UPDATE exchange_history_jobs SET
                       cursors=jsonb_set(cursors,ARRAY[$2],to_jsonb($3::bigint),true),
                       timeframe_counts=jsonb_set(timeframe_counts,ARRAY[$2],to_jsonb($4::int),true),
                       ingested=ingested+$5,requests=requests+1,updated_at=now() WHERE id=$1::uuid""",
                    job_id,timeframe,oldest,count,added,
                )
                await self.update_timeframe(job_id,timeframe,details)
                if len(page)<300 or (lower_bound is not None and oldest<=lower_bound):break
            details["status"]="COMPLETED";details["progress"]=100;await self.update_timeframe(job_id,timeframe,details)
            completed=await self.db.fetchval(
                "SELECT count(*) FROM exchange_history_jobs j CROSS JOIN LATERAL jsonb_each(j.timeframe_status) e WHERE j.id=$1::uuid AND e.value->>'status'='COMPLETED'",
                job_id,
            )
            await self.db.execute("UPDATE exchange_history_jobs SET progress=$2 WHERE id=$1::uuid",job_id,min(99,int(completed/max(1,len(job["timeframes"]))*100)))
        except asyncio.CancelledError:raise
        except Exception as exc:
            details["status"]="FAILED";details["error"]=str(exc)[:500];await self.update_timeframe(job_id,timeframe,details)
    async def update_timeframe(self,job_id,timeframe,details):
        await self.db.execute(
            "UPDATE exchange_history_jobs SET timeframe_status=jsonb_set(timeframe_status,ARRAY[$2],$3::jsonb,true),updated_at=now() WHERE id=$1::uuid",
            job_id,timeframe,json.dumps(details),
        )
        job=await self.history_job(job_id)
        progress=int(sum(item.get("progress",100 if item["status"]=="COMPLETED" else 0)
                         for item in job["timeframe_status"].values())/max(1,len(job["timeframe_status"])))
        await self.db.execute("UPDATE exchange_history_jobs SET progress=$2 WHERE id=$1::uuid AND status<>'COMPLETED'",job_id,min(99,progress))
        job["progress"]=100 if job["status"]=="COMPLETED" else min(99,progress)
        await self.publish_history(job)
    async def publish_history(self,job):
        if not job:return
        event={"event_type":"history.loading_progress","source":"exchange-gateway","timestamp":int(time()*1000),"payload":job}
        await self.redis.publish("history.update",json.dumps(event,separators=(",",":"),default=str))
    async def rebuild_elliott(self,symbol,timeframes):
        try:
            response=await self.client.post(
                self.s.elliott_service_url+"/internal/rebuild",
                json={"symbol":symbol,"timeframes":timeframes,"limit":500},timeout=120,
            )
            response.raise_for_status()
        except Exception as exc:
            self.last_error=f"elliott rebuild: {type(exc).__name__}: {exc}"[:500]
    async def private(self,method,path,payload=None):
        if not all((self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)):raise ValueError("OKX API credentials are not configured")
        body=json.dumps(payload,separators=(",",":")) if payload else "";headers=auth_headers(self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase,method,path,body,self.s.okx_demo)
        try:
            r=await self.client.request(method,self.s.okx_rest_url+path,content=body or None,headers=headers)
            r.raise_for_status()
        except httpx.HTTPStatusError as exc:
            response=exc.response
            details=" ".join(response.text.split())[:300] or response.reason_phrase
            error=ExchangeAmbiguousError if response.status_code>=500 else ValueError
            raise error(f"OKX HTTP {response.status_code}: {details}") from exc
        except httpx.RequestError as exc:
            raise ExchangeAmbiguousError(f"OKX request failed: {type(exc).__name__}: {exc}") from exc
        try:result=r.json()
        except ValueError as exc:raise ExchangeAmbiguousError("OKX returned an invalid JSON response") from exc
        if not isinstance(result,dict):raise ExchangeAmbiguousError("OKX returned an invalid response")
        if result.get("code")!="0":
            details=okx_error_details(result)
            raise ValueError(f"OKX request rejected: {json.dumps(details,separators=(',',':'))}")
        data=result.get("data")
        if not isinstance(data,list):raise ExchangeAmbiguousError("OKX response does not contain a data array")
        return data
