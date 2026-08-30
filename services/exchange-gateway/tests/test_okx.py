from src.okx import auth_headers,book,candle,trade,ws_login
from src.service import incremental_start,instrument_spec
def test_signature_matches_known_hmac():
    h=auth_headers("k","s","p","GET","/api/v5/account/balance",stamp="2020-01-01T00:00:00.000Z");assert h["OK-ACCESS-SIGN"]=="3+YzNZYq3N3si/o/YkbHvC4RpV8WeOY5ZpO7abfFcYA=";assert h["x-simulated-trading"]=="1"
def test_private_websocket_login_signature():
    value=ws_login("k","s","p",stamp="1538054050")
    assert value["op"]=="login" and value["args"][0]["timestamp"]=="1538054050"
    assert value["args"][0]["sign"]=="4wFKSrXaG6EYOdbv/KEKJIOMEzKwShv8qgkR1OcPdvE="
def test_normalizers():
    assert candle(["1","2","4","1","3","9","0","0","1"],"BTC-USDT","M1")["is_closed"]
    assert trade({"instId":"BTC-USDT","tradeId":"7","ts":"1","px":"2","sz":"3","side":"buy"})["side"]=="buy"
    assert book({"ts":"1","seqId":"2","bids":[["2","3","1"]],"asks":[["4","5","1"]]},"BTC-USDT")["sequenceId"]==2

def test_incremental_start_uses_next_timeframe_boundary():
    assert incremental_start("M1",1_000_000,100)==1_060_000
    assert incremental_start("H4",1_000_000,100)==15_400_000

def test_incremental_start_falls_back_for_empty_timeframe():
    assert incremental_start("D1",None,123)==123

def test_swap_contract_sizes_are_converted_to_base_asset_units():
    spec=instrument_spec({"tickSz":"0.1","lotSz":"0.01","minSz":"0.01","ctVal":"0.01"})
    assert spec["tick_size"]==.1
    assert spec["lot_size"]==.0001
    assert spec["minimum_order_size"]==.0001
    assert spec["contract_value"]==.01
