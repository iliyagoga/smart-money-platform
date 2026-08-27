import asyncio,json
from fastapi import HTTPException,WebSocket,WebSocketDisconnect

CHANNELS={"candle.update","trade.executed","orderbook.updated","structure.update","smc.update","signal.update","position.update","system.state","system.control"}

def websocket_token(ws:WebSocket)->str|None:
    protocols=[x.strip() for x in ws.headers.get("sec-websocket-protocol","").split(",")]
    if len(protocols)>=2 and protocols[0]=="access_token":return protocols[1]
    return ws.query_params.get("access_token")
def matches(event:dict,event_types:set[str],symbols:set[str])->bool:
    event_type=event.get("event_type","");payload=event.get("payload") or {};symbol=payload.get("symbol")
    type_ok="*" in event_types or event_type in event_types or any(x.endswith(".*") and event_type.startswith(x[:-1]) for x in event_types)
    return type_ok and (not symbols or symbol is None or symbol in symbols)
def parse_subscription(message:dict,event_types:set[str],symbols:set[str]):
    operation=message.get("op");types={str(x) for x in message.get("events",[])};requested_symbols={str(x).upper() for x in message.get("symbols",[])}
    if operation=="subscribe":event_types.update(types);symbols.update(requested_symbols)
    elif operation=="unsubscribe":event_types.difference_update(types);symbols.difference_update(requested_symbols)
    return {"op":"subscribed","events":sorted(event_types),"symbols":sorted(symbols)}

class WebSocketBridge:
    def __init__(self,redis,verifier):self.redis=redis;self.verifier=verifier;self.connections=0
    async def serve(self,ws:WebSocket):
        token=websocket_token(ws)
        if not token:await ws.close(code=4401,reason="Access token required");return
        try:principal=await self.verifier.verify(token)
        except HTTPException:await ws.close(code=4401,reason="Invalid access token");return
        await ws.accept(subprotocol="access_token" if ws.headers.get("sec-websocket-protocol","").startswith("access_token") else None);self.connections+=1
        pubsub=self.redis.pubsub();await pubsub.subscribe(*CHANNELS);event_types:set[str]=set();symbols:set[str]=set()
        await ws.send_json({"op":"ready","user":principal.username,"roles":sorted(principal.roles)})
        async def receive():
            while True:
                message=await ws.receive_json()
                if message.get("op")=="ping":await ws.send_json({"op":"pong"})
                elif message.get("op") in {"subscribe","unsubscribe"}:await ws.send_json(parse_subscription(message,event_types,symbols))
                else:await ws.send_json({"op":"error","message":"Unsupported operation"})
        async def publish():
            async for message in pubsub.listen():
                if message["type"]!="message":continue
                try:event=json.loads(message["data"])
                except (TypeError,json.JSONDecodeError):continue
                if matches(event,event_types,symbols):await ws.send_json(event)
        tasks=[asyncio.create_task(receive()),asyncio.create_task(publish())]
        try:
            done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in done:task.result()
        except (WebSocketDisconnect,RuntimeError):pass
        finally:
            for task in tasks:task.cancel()
            await pubsub.aclose();self.connections-=1
