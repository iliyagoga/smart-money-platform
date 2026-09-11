import asyncio
from time import time

import pytest
from src.security import Principal
from src.websocket import matches,parse_subscription,websocket_token
def test_subscription_and_symbol_filter():
    events=set();symbols=set();result=parse_subscription({"op":"subscribe","events":["candle.*"],"symbols":["btc-usdt-swap"]},events,symbols)
    assert result["symbols"]==["BTC-USDT-SWAP"]
    assert matches({"event_type":"candle.update","payload":{"symbol":"BTC-USDT-SWAP"}},events,symbols)
    assert not matches({"event_type":"candle.update","payload":{"symbol":"ETH-USDT-SWAP"}},events,symbols)
def test_global_events_without_symbol_pass_filter():
    assert matches({"event_type":"config.updated","payload":{}},{"config.updated"},{"BTC-USDT-SWAP"})
def test_unsubscribe_removes_event():
    events={"position.*"};symbols=set();parse_subscription({"op":"unsubscribe","events":["position.*"]},events,symbols);assert not events
def test_subscription_rejects_unknown_or_oversized_filters():
    with pytest.raises(ValueError,match="Unsupported"):
        parse_subscription({"op":"subscribe","events":["system.control"]},set(),set())
    with pytest.raises(ValueError,match="too large"):
        parse_subscription({"op":"subscribe","events":[],"symbols":[f"S{i}" for i in range(51)]},set(),set())
def test_websocket_tokens_in_query_strings_are_rejected():
    class Socket:
        headers={};query_params={"access_token":"leaked-token"}
    assert websocket_token(Socket()) is None


def test_websocket_closes_when_access_token_expires():
    class Verifier:
        async def verify(self, token):
            return Principal("id", "user", frozenset({"viewer"}), {"exp": time() - 1})

    class PubSub:
        async def subscribe(self, *channels):pass
        async def aclose(self):pass
        async def listen(self):
            while True:
                await asyncio.sleep(3600)
                yield {}

    class Redis:
        def pubsub(self):return PubSub()

    class Socket:
        headers={"sec-websocket-protocol":"access_token, token","origin":"https://app.example.com"}
        closed=[]
        async def accept(self,subprotocol):pass
        async def send_json(self,message):pass
        async def receive_json(self):await asyncio.sleep(3600)
        async def close(self,code,reason):self.closed.append((code,reason))

    from src.websocket import WebSocketBridge
    bridge=WebSocketBridge(Redis(),Verifier(),{"https://app.example.com"},1)
    socket=Socket()
    asyncio.run(bridge.serve(socket))
    assert socket.closed==[(4401,"Access token expired")]
    assert bridge.connections==0


def test_websocket_limits_connections_per_user():
    class Verifier:
        async def verify(self,token):
            return Principal("id","user",frozenset({"viewer"}),{"exp":time()+60})
    class Socket:
        headers={"sec-websocket-protocol":"access_token, token"}
        closed=[]
        async def close(self,code,reason):self.closed.append((code,reason))

    from src.websocket import WebSocketBridge
    bridge=WebSocketBridge(object(),Verifier(),max_connections=10,max_connections_per_user=1)
    bridge.user_connections["id"]=1
    socket=Socket()
    asyncio.run(bridge.serve(socket))
    assert socket.closed==[(4429,"Too many connections for this user")]
    assert bridge.connections==0
    assert bridge.user_connections=={"id":1}
