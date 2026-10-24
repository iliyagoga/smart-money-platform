import asyncio
import json
from time import time

import pytest
from fastapi import WebSocketDisconnect
from src.security import Principal
from src.websocket import matches,parse_subscription,websocket_token
def test_subscription_and_symbol_filter():
    events=set();symbols=set();result=parse_subscription({"op":"subscribe","events":["candle.*"],"symbols":["btc-usdt-swap"]},events,symbols)
    assert result["symbols"]==["BTC-USDT-SWAP"]
    assert matches({"event_type":"candle.update","payload":{"symbol":"BTC-USDT-SWAP"}},events,symbols)
    assert not matches({"event_type":"candle.update","payload":{"symbol":"ETH-USDT-SWAP"}},events,symbols)
def test_history_progress_subscription_uses_symbol_filter():
    events=set();symbols=set()
    parse_subscription({"op":"subscribe","events":["history.*"],"symbols":["BTC-USDT-SWAP"]},events,symbols)
    assert matches({"event_type":"history.loading_progress","payload":{"symbol":"BTC-USDT-SWAP"}},events,symbols)
    assert not matches({"event_type":"history.calculation_progress","payload":{"symbol":"ETH-USDT-SWAP"}},events,symbols)
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


@pytest.mark.parametrize("field",["events","symbols"])
@pytest.mark.parametrize("value",[None,1,"candle.*",{},[None],[{}]])
def test_subscription_rejects_malformed_filters_without_mutation(field,value):
    events={"candle.*"};symbols={"BTC-USDT-SWAP"}
    with pytest.raises(ValueError,match="lists of strings"):
        parse_subscription({"op":"subscribe",field:value},events,symbols)
    assert events=={"candle.*"} and symbols=={"BTC-USDT-SWAP"}


def test_subscription_limit_applies_across_messages_and_unsubscribe_frees_capacity():
    events=set();symbols=set()
    parse_subscription({"op":"subscribe","symbols":[f"S{i}" for i in range(50)]},events,symbols)
    parse_subscription({"op":"subscribe","symbols":["S0"]},events,symbols)
    with pytest.raises(ValueError,match="too large"):
        parse_subscription({"op":"subscribe","events":["candle.*"],"symbols":["NEW"]},events,symbols)
    assert len(symbols)==50 and "NEW" not in symbols and not events
    parse_subscription({"op":"unsubscribe","symbols":["S0"]},events,symbols)
    parse_subscription({"op":"subscribe","symbols":["NEW"]},events,symbols)
    assert len(symbols)==50 and "NEW" in symbols


@pytest.mark.parametrize("event",[
    {"event_type":[],"payload":{}},
    {"event_type":"candle.update","payload":[1]},
    {"event_type":"candle.update","payload":{"symbol":[]}},
])
def test_malformed_published_events_do_not_break_filtering(event):
    assert not matches(event,{"candle.*"},{"BTC-USDT-SWAP"})


def test_websocket_recovers_from_bad_messages_and_cleans_up():
    class Verifier:
        async def verify(self,token):
            return Principal("id","user",frozenset({"viewer"}),{"exp":time()+60})
    class PubSub:
        closed=False
        async def subscribe(self,*channels):pass
        async def aclose(self):self.closed=True
        async def listen(self):
            while True:
                await asyncio.sleep(3600)
                yield {}
    pubsub=PubSub()
    class Redis:
        def pubsub(self):return pubsub
    class Socket:
        headers={"sec-websocket-protocol":"access_token, token"}
        messages=[]
        incoming=iter(["invalid",{"op":[]},{"op":{}},{"op":"subscribe","symbols":None},{"op":"ping"}])
        async def accept(self,subprotocol):pass
        async def send_json(self,message):self.messages.append(message)
        async def receive_json(self):
            value=next(self.incoming,None)
            if value is None:raise WebSocketDisconnect()
            if isinstance(value,str):return json.loads(value)
            return value
    from src.websocket import WebSocketBridge
    bridge=WebSocketBridge(Redis(),Verifier());socket=Socket()
    asyncio.run(bridge.serve(socket))
    assert [message["op"] for message in socket.messages]==["ready","error","error","error","error","pong"]
    assert pubsub.closed and bridge.connections==0 and not bridge.user_connections


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
