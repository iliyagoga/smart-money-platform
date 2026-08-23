import asyncio,json,random
import httpx,websockets
from .okx import TIMEFRAMES,REVERSE_TIMEFRAMES,auth_headers,book,candle,trade

class ExchangeGateway:
    def __init__(self,s):
        self.s=s;self.client=None;self.tasks=[];self.connected={"public":False,"business":False};self.last_error=None;self.history_jobs={}
    async def start(self):
        self.client=httpx.AsyncClient(timeout=20)
        if self.s.market_data_enabled:
            self.tasks=[asyncio.create_task(self.loop("public",self.s.okx_public_ws_url)),asyncio.create_task(self.loop("business",self.s.okx_business_ws_url))]
    async def stop(self):
        for task in self.tasks:task.cancel()
        if self.client:await self.client.aclose()
    @property
    def symbols(self):return [x.strip().upper() for x in self.s.symbols.split(",") if x.strip()]
    @property
    def timeframes(self):return [x.strip().upper() for x in self.s.timeframes.split(",") if x.strip() in TIMEFRAMES]
    async def loop(self,name,url):
        delay=1
        while True:
            try:
                async with websockets.connect(url,ping_interval=20,ping_timeout=10,max_size=2**22) as ws:
                    self.connected[name]=True;delay=1
                    args=[]
                    if name=="public":args=[{"channel":c,"instId":s} for s in self.symbols for c in ("trades","books5")]
                    else:args=[{"channel":"candle"+TIMEFRAMES[t],"instId":s} for s in self.symbols for t in self.timeframes]
                    await ws.send(json.dumps({"op":"subscribe","args":args}))
                    async for raw in ws:await self.handle(json.loads(raw))
            except asyncio.CancelledError:raise
            except Exception as exc:self.last_error=type(exc).__name__;self.connected[name]=False;await asyncio.sleep(delay+random.random());delay=min(delay*2,60)
    async def ingest(self,path,payload):
        response=await self.client.post(self.s.data_service_url+path,json=payload,headers={"X-Correlation-ID":"okx-"+str(payload.get("timestamp",0))});response.raise_for_status()
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
    async def history(self,symbol,timeframe,limit=100):
        params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":min(limit,300)};r=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params);r.raise_for_status();body=r.json()
        if body.get("code")!="0":raise ValueError(body.get("msg","OKX error"))
        values=[candle(x,symbol,timeframe) for x in body["data"]]
        for value in reversed(values):await self.ingest("/internal/ingest/candles",value)
        return len(values)
    async def history_page(self,symbol,timeframe,after=None):
        params={"instId":symbol,"bar":TIMEFRAMES[timeframe],"limit":300}
        if after is not None:params["after"]=str(after)
        response=await self.client.get(self.s.okx_rest_url+"/api/v5/market/history-candles",params=params)
        response.raise_for_status();body=response.json()
        if body.get("code")!="0":raise ValueError(body.get("msg","OKX error"))
        return [candle(item,symbol,timeframe) for item in body["data"]]
    def schedule_history(self,job_id,symbol,timeframes,start,end,max_candles):
        self.history_jobs[job_id]={
            "id":job_id,"status":"QUEUED","symbol":symbol,"timeframes":timeframes,"from":start,"to":end,
            "max_candles":max_candles,"ingested":0,"requests":0,"progress":0,"error":None,
        }
        task=asyncio.create_task(self.download_history(job_id));self.tasks.append(task)
    async def download_history(self,job_id):
        job=self.history_jobs[job_id];job["status"]="RUNNING"
        try:
            total_target=job["max_candles"]*len(job["timeframes"])
            for timeframe in job["timeframes"]:
                cursor=job["to"]
                timeframe_count=0
                while timeframe_count<job["max_candles"]:
                    page=await self.history_page(job["symbol"],timeframe,cursor)
                    job["requests"]+=1
                    if not page:break
                    eligible=[item for item in page if item["is_closed"] and (job["from"] is None or item["timestamp"]>=job["from"])]
                    remaining=job["max_candles"]-timeframe_count;eligible=eligible[:remaining]
                    await self.ingest_batch(list(reversed(eligible)))
                    timeframe_count+=len(eligible);job["ingested"]+=len(eligible)
                    oldest=min(item["timestamp"] for item in page)
                    job["cursor"]={"timeframe":timeframe,"timestamp":oldest}
                    job["progress"]=min(99,int(job["ingested"]/max(1,total_target)*100))
                    if len(page)<300 or (job["from"] is not None and oldest<=job["from"]):break
                    cursor=oldest
                    await asyncio.sleep(.12)
            job["status"]="COMPLETED";job["progress"]=100
        except Exception as exc:
            job["status"]="FAILED";job["error"]=str(exc)[:2000]
    async def private(self,method,path,payload=None):
        if not all((self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase)):raise ValueError("OKX API credentials are not configured")
        body=json.dumps(payload,separators=(",",":")) if payload else "";headers=auth_headers(self.s.okx_api_key,self.s.okx_secret_key,self.s.okx_passphrase,method,path,body,self.s.okx_demo)
        r=await self.client.request(method,self.s.okx_rest_url+path,content=body or None,headers=headers);r.raise_for_status();result=r.json()
        if result.get("code")!="0":raise ValueError(result.get("msg","OKX error"))
        return result["data"]
