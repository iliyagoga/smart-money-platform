from src.websocket import matches,parse_subscription
def test_subscription_and_symbol_filter():
    events=set();symbols=set();result=parse_subscription({"op":"subscribe","events":["candle.*"],"symbols":["btc-usdt-swap"]},events,symbols)
    assert result["symbols"]==["BTC-USDT-SWAP"]
    assert matches({"event_type":"candle.update","payload":{"symbol":"BTC-USDT-SWAP"}},events,symbols)
    assert not matches({"event_type":"candle.update","payload":{"symbol":"ETH-USDT-SWAP"}},events,symbols)
def test_global_events_without_symbol_pass_filter():
    assert matches({"event_type":"config.updated","payload":{}},{"config.updated"},{"BTC-USDT-SWAP"})
def test_unsubscribe_removes_event():
    events={"position.*"};symbols=set();parse_subscription({"op":"unsubscribe","events":["position.*"]},events,symbols);assert not events
