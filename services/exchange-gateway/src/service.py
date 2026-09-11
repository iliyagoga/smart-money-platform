import asyncio,json,logging,random
from time import monotonic,time
import asyncpg,httpx,websockets
from decimal import Decimal,ROUND_HALF_UP
from urllib.parse import urlencode
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from .okx import TIMEFRAMES,REVERSE_TIMEFRAMES,auth_headers,book,candle,trade,ws_login

log=logging.getLogger(__name__)

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

class ExchangeGateway:
    def __init__(self,s):
        self.s=s;self.client=None;self.db=None;self.redis=None;self.tasks=set();self.connected={"public":False,"business":False,"private":False};self.last_error=None
        self.history_semaphore=asyncio.Semaphore(s.history_concurrency);self.running_history=set()
        self.active_symbols=[];self.websockets={};self.market_page_cache={};self.market_page_locks={};self.private_ready=asyncio.Event();self.pending={}
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
        await self.db.execute("ALTER TABLE exchange_orders ADD COLUMN IF NOT EXISTS exit_algo_cl_ord_id text")
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
        if self.s.trading_enabled:
            if not all((self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)):
                self.last_error="Private trading enabled but OKX credentials are not configured"
            else:
                self.add_task(self.private_loop());self.add_task(self.consume_orders())
    async def stop(self):
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        if self.client:await self.client.aclose()
        if self.redis:await self.redis.aclose()
        if self.db:await self.db.close()
    def add_task(self,coroutine):
        task=asyncio.create_task(coroutine);self.tasks.add(task);task.add_done_callback(self.tasks.discard);return task
    @property
    def symbols(self):return self.active_symbols or [x.strip().upper() for x in self.s.symbols.split(",") if x.strip()]
    @property
    def timeframes(self):return [x.strip().upper() for x in self.s.timeframes.split(",") if x.strip() in TIMEFRAMES]
    async def loop(self,name,url):
        delay=1
        while True:
            try:
                async with websockets.connect(url,ping_interval=20,ping_timeout=10,max_size=2**22) as ws:
                    self.websockets[name]=ws
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
    async def refresh_symbols(self):
        try:rows=await self.db.fetch("SELECT symbol FROM trading_assets WHERE enabled ORDER BY symbol")
        except asyncpg.UndefinedTableError:rows=[]
        self.active_symbols=[row["symbol"] for row in rows]
        await self.refresh_instrument_specs(self.active_symbols)
        for connection in list(self.websockets.values()):await connection.close()
        return self.symbols
    async def refresh_instrument_specs(self,symbols):
        for symbol in symbols:
            try:
                response=await self.client.get(
                    self.s.okx_rest_url+"/api/v5/public/instruments",params={"instType":"SWAP","instId":symbol},
                )
                response.raise_for_status();body=response.json();items=body.get("data") or []
                if body.get("code")!="0" or not items:continue
                instrument=items[0];spec=instrument_spec(instrument)
                funding_response=await self.client.get(self.s.okx_rest_url+"/api/v5/public/funding-rate",params={"instId":symbol})
                funding_body=funding_response.json();funding=(funding_body.get("data") or [{}])[0]
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
            except Exception as exc:
                self.last_error=f"instrument metadata {symbol}: {type(exc).__name__}: {exc}"[:500]
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
            if channel.startswith("candle"):await self.ingest("/internal/ingest/candles",candle(item,symbol,REVERSE_TIMEFRAMES[channel[6:]]))
            elif channel=="trades":await self.ingest("/internal/ingest/ticks",trade(item))
            elif channel=="books5":await self.ingest("/internal/ingest/orderbook",book(item,symbol))
    async def private_loop(self):
        delay=1
        while True:
            try:
                async with websockets.connect(self.s.okx_private_ws_url,ping_interval=20,ping_timeout=10,max_size=2**22) as ws:
                    self.websockets["private"]=ws;self.connected["private"]=True
                    await ws.send(json.dumps(ws_login(self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)))
                    async for raw in ws:
                        msg=json.loads(raw)
                        if msg.get("event")=="login" and msg.get("code")=="0":
                            await ws.send(json.dumps({"op":"subscribe","args":[{"channel":"orders","instType":"ANY"}]}));self.private_ready.set();delay=1;continue
                        await self.handle_private(msg)
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.last_error=f"private: {type(exc).__name__}: {exc}"[:500]
            finally:
                self.private_ready.clear();self.connected["private"]=False;self.websockets.pop("private",None)
            await asyncio.sleep(delay+random.random());delay=min(delay*2,60)  # nosec B311
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
                eo.exit_algo_cl_ord_id=$2 AS position_exit
              FROM exchange_orders eo LEFT JOIN orders o ON o.id=eo.local_order_id
              LEFT JOIN trading_assets ta ON ta.symbol=eo.symbol
              WHERE eo.cl_ord_id=$1 OR eo.exit_algo_cl_ord_id=$2""",cl_ord_id,algo_cl_ord_id)
            if not row:continue
            state=item.get("state","").upper();mapping={"LIVE":"OPEN","PARTIALLY_FILLED":"PARTIALLY_FILLED","FILLED":"FILLED","CANCELED":"CANCELLED","MMP_CANCELED":"CANCELLED"};status=mapping.get(state,state)
            if not row["position_exit"]:
                await self.db.execute("UPDATE exchange_orders SET exchange_order_id=$2,status=$3,payload=$4::jsonb,updated_at=now() WHERE cl_ord_id=$1",cl_ord_id,item.get("ordId"),status,json.dumps(item))
            await self.record_trading_log({"id":str(row["local_order_id"]),"symbol":item.get("instId","UNKNOWN"),
              "execution_mode":row["execution_mode"] or ("DEMO" if self.s.okx_demo else "PRODUCTION")},
              "ORDER_UPDATE",status,{"exchange_order_id":item.get("ordId"),"exchange":item})
            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{"order_id":str(row["local_order_id"]),"exchange_order_id":item.get("ordId"),"status":status,"filled_price":float(item.get("avgPx") or item.get("fillPx") or 0),"filled_quantity":float(item.get("accFillSz") or 0)*float(row["contract_value"]),"raw_state":state,"position_exit":bool(row["position_exit"]),"reason":"EXCHANGE_PROTECTIVE_EXIT" if row["position_exit"] else None}})},maxlen=100000,approximate=True)
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
        try:await self.redis.xgroup_create("execution.command",group,id="$",mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):raise
        while True:
            batches=await self.redis.xreadgroup(group,"exchange-1",{"execution.command":">"},count=10,block=2000)
            for _,messages in batches:
                for message_id,fields in messages:
                    try:
                        event=json.loads(fields["data"]);payload=event.get("payload",{})
                        if event.get("event_type")=="order.request":await self.place_order(payload)
                        elif event.get("event_type")=="order.cancel_requested":await self.cancel_order(payload["order_id"])
                        await self.redis.xack("execution.command",group,message_id)
                    except asyncio.CancelledError:raise
                    except Exception as exc:
                        self.last_error=f"order command: {type(exc).__name__}: {exc}"[:500]
                        payload=(json.loads(fields["data"]).get("payload") or {})
                        log.exception("Order command failed: local_order_id=%s",payload.get("id"))
                        if payload.get("id"):
                            await self.db.execute("""UPDATE exchange_orders SET status='REJECTED',
                              payload=payload||jsonb_build_object('error',$2::text),updated_at=now()
                              WHERE local_order_id=$1::uuid""",payload["id"],str(exc))
                            await self.record_trading_log(payload,"ORDER_REJECTED","REJECTED",{"reason":str(exc)})
                            await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{"order_id":payload["id"],"status":"REJECTED","reason":str(exc)}})},maxlen=100000,approximate=True)
                        await self.redis.xack("execution.command",group,message_id)
    async def instrument_order_spec(self,symbol):
        row=await self.db.fetchrow("SELECT contract_value,lot_size,minimum_order_size,tick_size,validation_status FROM trading_assets WHERE symbol=$1",symbol)
        if not row or row["validation_status"]!="ACTIVE":raise ValueError("Exchange instrument metadata is unavailable")
        return row
    async def trading_instrument_spec(self,symbol):
        mode="OKX Demo" if self.s.okx_demo else "OKX Production"
        path="/api/v5/account/instruments?"+urlencode({"instType":"SWAP","instId":symbol})
        try:items=await self.private("GET",path)
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
        await self.require_safe_account_config()
        await self.instrument_order_spec(payload["symbol"])
        spec=await self.trading_instrument_spec(payload["symbol"]);contract=Decimal(str(spec["contract_value"]));base_qty=Decimal(str(payload["quantity"]))
        contracts=base_qty/contract;lot_contracts=Decimal(str(spec["lot_size"]))/contract
        contracts=(contracts//lot_contracts)*lot_contracts
        minimum=Decimal(str(spec["minimum_order_size"]))/contract
        if contracts<minimum:raise ValueError("Order quantity is below OKX minSz")
        leverage=int(payload.get("leverage",1));margin_mode=payload.get("margin_mode") or self.s.margin_mode
        if not payload.get("reduce_only"):
            await self.private("POST","/api/v5/account/set-leverage",{"instId":payload["symbol"],"lever":str(leverage),"mgnMode":margin_mode})
        local_id=payload["id"];cl_ord_id="SMP"+local_id.replace("-","")[:29]
        args={"instId":payload["symbol"],"tdMode":margin_mode,"side":payload["side"].lower(),"ordType":payload["type"].lower(),"sz":format(contracts,"f"),"clOrdId":cl_ord_id,"tag":"SMPELLIOTT"}
        if payload.get("price") is not None and payload["type"]!="MARKET":args["px"]=price_to_tick(payload["price"],spec["tick_size"])
        attached={};exit_algo_cl_ord_id=None
        if payload.get("stop_loss_price") is not None:attached.update({"slTriggerPx":price_to_tick(payload["stop_loss_price"],spec["tick_size"]),"slOrdPx":"-1"})
        if payload.get("take_profit_prices"):attached.update({"tpTriggerPx":price_to_tick(payload["take_profit_prices"][0],spec["tick_size"]),"tpOrdPx":"-1"})
        if attached:
            exit_algo_cl_ord_id="SMA"+local_id.replace("-","")[:29];attached["attachAlgoClOrdId"]=exit_algo_cl_ord_id
            args["attachAlgoOrds"]=[attached]
        if payload.get("reduce_only"):args["reduceOnly"]=True
        await self.db.execute("INSERT INTO exchange_orders(local_order_id,cl_ord_id,symbol,status,payload,exit_algo_cl_ord_id) VALUES($1::uuid,$2,$3,'SUBMITTING',$4::jsonb,$5) ON CONFLICT(local_order_id) DO NOTHING",local_id,cl_ord_id,payload["symbol"],json.dumps(args),exit_algo_cl_ord_id)
        await self.record_trading_log(payload,"ORDER_SUBMITTING","SUBMITTING",{"request":args})
        ack=okx_ack(await self.private("POST","/api/v5/trade/order",args),"order")
        await self.db.execute("UPDATE exchange_orders SET exchange_order_id=$2,status='ACCEPTED',updated_at=now() WHERE local_order_id=$1::uuid",local_id,ack.get("ordId"))
        await self.record_trading_log(payload,"ORDER_ACCEPTED","ACCEPTED",{"exchange":ack})
        await self.redis.xadd("trading.command",{"data":json.dumps({"event_type":"exchange.order_updated","payload":{"order_id":local_id,"exchange_order_id":ack.get("ordId"),"status":"OPEN"}})},maxlen=100000,approximate=True)
        return {"order_id":local_id,"exchange_order_id":ack.get("ordId"),"status":"ACCEPTED"}
    async def cancel_order(self,local_order_id):
        row=await self.db.fetchrow("""SELECT eo.cl_ord_id,eo.symbol,eo.status,o.data->>'execution_mode' AS execution_mode
          FROM exchange_orders eo LEFT JOIN orders o ON o.id=eo.local_order_id WHERE eo.local_order_id=$1::uuid""",local_order_id)
        if not row:raise ValueError("Order is not owned by this system")
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
        params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":min(limit,300)};r=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params);r.raise_for_status();body=r.json()
        if body.get("code")!="0":raise ValueError(body.get("msg","OKX error"))
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
            response=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params)
            response.raise_for_status();body=response.json()
            if body.get("code")!="0":raise ValueError(body.get("msg","OKX error"))
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
        response=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params)
        response.raise_for_status();body=response.json()
        if body.get("code")!="0":raise ValueError(body.get("msg","OKX error"))
        return [candle(item,symbol,timeframe) for item in body["data"]]
    async def create_history(self,job_id,symbol,timeframes,start,end,incremental=False,backfill=False):
        statuses={timeframe:{"status":"QUEUED","ingested":0,"requests":0,"error":None} for timeframe in timeframes}
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
            "BACKFILL" if backfill else ("INCREMENTAL" if incremental else "FULL"), json.dumps(timeframe_to),
        )
        self.schedule_history(job_id);return await self.history_job(job_id)
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
        return await self.history_job(job_id)
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
                    await self.db.execute("UPDATE exchange_history_jobs SET status='FAILED',error=$2,updated_at=now() WHERE id=$1::uuid",job_id,error[:2000]);return
                await self.db.execute("UPDATE exchange_history_jobs SET status='COMPLETED',progress=100,updated_at=now() WHERE id=$1::uuid",job_id)
                self.add_task(self.rebuild_elliott(job["symbol"],job["timeframes"]))
            except asyncio.CancelledError:raise
            except Exception as exc:
                await self.db.execute("UPDATE exchange_history_jobs SET status='FAILED',error=$2,updated_at=now() WHERE id=$1::uuid",job_id,str(exc)[:2000])
    async def download_timeframe(self,job_id,job,timeframe):
        details=job["timeframe_status"].get(timeframe,{"status":"QUEUED","ingested":0,"requests":0,"error":None})
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
                oldest=min(item["timestamp"] for item in page);cursor=oldest
                await self.db.execute(
                    """UPDATE exchange_history_jobs SET
                       cursors=jsonb_set(cursors,ARRAY[$2],to_jsonb($3::bigint),true),
                       timeframe_counts=jsonb_set(timeframe_counts,ARRAY[$2],to_jsonb($4::int),true),
                       ingested=ingested+$5,requests=requests+1,updated_at=now() WHERE id=$1::uuid""",
                    job_id,timeframe,oldest,count,added,
                )
                await self.update_timeframe(job_id,timeframe,details)
                if len(page)<300 or (lower_bound is not None and oldest<=lower_bound):break
                await asyncio.sleep(.12)
            details["status"]="COMPLETED";await self.update_timeframe(job_id,timeframe,details)
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
        r=await self.client.request(method,self.s.okx_rest_url+path,content=body or None,headers=headers);r.raise_for_status();result=r.json()
        if result.get("code")!="0":
            details=okx_error_details(result)
            raise ValueError(f"OKX request rejected: {json.dumps(details,separators=(',',':'))}")
        return result["data"]
