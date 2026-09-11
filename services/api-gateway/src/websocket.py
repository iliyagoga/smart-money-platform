import asyncio,json
from time import time
from fastapi import HTTPException,WebSocket,WebSocketDisconnect

CHANNELS={"candle.update","trade.executed","orderbook.updated","scenario.update","position.update","trading.config","system.state","system.control"}
SUBSCRIPTION_EVENTS={"candle.*","trade.executed","orderbook.updated","scenario.*","order.*","position.*","trading.config.*","system.state"}

def websocket_token(ws:WebSocket)->str|None:
    protocols=[x.strip() for x in ws.headers.get("sec-websocket-protocol","").split(",")]
    if len(protocols)>=2 and protocols[0]=="access_token":return protocols[1]
    return None
def matches(event:dict,event_types:set[str],symbols:set[str])->bool:
    event_type=event.get("event_type","");payload=event.get("payload") or {};symbol=payload.get("symbol")
    type_ok="*" in event_types or event_type in event_types or any(x.endswith(".*") and event_type.startswith(x[:-1]) for x in event_types)
    return type_ok and (not symbols or symbol is None or symbol in symbols)
def parse_subscription(message:dict,event_types:set[str],symbols:set[str]):
    operation=message.get("op");types={str(x) for x in message.get("events",[])};requested_symbols={str(x).upper() for x in message.get("symbols",[])}
    if len(types)>20 or len(requested_symbols)>50:raise ValueError("Subscription is too large")
    if types-SUBSCRIPTION_EVENTS:raise ValueError("Unsupported event subscription")
    if any(not symbol or len(symbol)>80 for symbol in requested_symbols):raise ValueError("Invalid symbol subscription")
    if operation=="subscribe":event_types.update(types);symbols.update(requested_symbols)
    elif operation=="unsubscribe":event_types.difference_update(types);symbols.difference_update(requested_symbols)
    return {"op":"subscribed","events":sorted(event_types),"symbols":sorted(symbols)}

class WebSocketBridge:
    def __init__(self,redis,verifier,allowed_origins=(),max_connections=200,max_connections_per_user=5):
        self.redis=redis;self.verifier=verifier;self.connections=0
        self.allowed_origins=frozenset(allowed_origins);self.max_connections=max_connections
        self.max_connections_per_user=max_connections_per_user;self.user_connections:dict[str,int]={}
        self.connection_lock=asyncio.Lock()
    async def serve(self,ws:WebSocket):
        origin=ws.headers.get("origin")
        if origin and origin not in self.allowed_origins:await ws.close(code=4403,reason="Origin is not allowed");return
        token=websocket_token(ws)
        if not token:await ws.close(code=4401,reason="Access token required");return
        async with self.connection_lock:
            if self.connections>=self.max_connections:
                await ws.close(code=4429,reason="Too many connections");return
            self.connections+=1
        user_reserved=False
        try:
            try:principal=await self.verifier.verify(token)
            except HTTPException:await ws.close(code=4401,reason="Invalid access token");return
            async with self.connection_lock:
                if self.user_connections.get(principal.subject,0)>=self.max_connections_per_user:
                    await ws.close(code=4429,reason="Too many connections for this user");return
                self.user_connections[principal.subject]=self.user_connections.get(principal.subject,0)+1
                user_reserved=True
            await ws.accept(subprotocol="access_token")
            pubsub=self.redis.pubsub();await pubsub.subscribe(*CHANNELS);event_types:set[str]=set();symbols:set[str]=set()
            await ws.send_json({"op":"ready","user":principal.username,"roles":sorted(principal.roles)})
            async def receive():
                while True:
                    message=await ws.receive_json()
                    if not isinstance(message,dict):await ws.send_json({"op":"error","message":"Invalid message"});continue
                    if message.get("op")=="ping":await ws.send_json({"op":"pong"})
                    elif message.get("op") in {"subscribe","unsubscribe"}:
                        try:response=parse_subscription(message,event_types,symbols)
                        except ValueError as exc:await ws.send_json({"op":"error","message":str(exc)});continue
                        await ws.send_json(response)
                    else:await ws.send_json({"op":"error","message":"Unsupported operation"})
            async def publish():
                async for message in pubsub.listen():
                    if message["type"]!="message":continue
                    try:event=json.loads(message["data"])
                    except (TypeError,json.JSONDecodeError):continue
                    if isinstance(event,dict) and matches(event,event_types,symbols):await ws.send_json(event)
            async def expire():
                await asyncio.sleep(max(0,float(principal.claims["exp"])-time()))
                await ws.close(code=4401,reason="Access token expired")
            tasks=[asyncio.create_task(receive()),asyncio.create_task(publish()),asyncio.create_task(expire())]
            try:
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:task.result()
            except (WebSocketDisconnect,RuntimeError):pass
            finally:
                for task in tasks:task.cancel()
                await pubsub.aclose()
        except (WebSocketDisconnect,RuntimeError):pass
        finally:
            async with self.connection_lock:
                self.connections-=1
                if user_reserved and self.user_connections.get(principal.subject,0):
                    remaining=self.user_connections[principal.subject]-1
                    if remaining:self.user_connections[principal.subject]=remaining
                    else:self.user_connections.pop(principal.subject,None)
