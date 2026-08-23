from src.okx import auth_headers,book,candle,trade
def test_signature_matches_known_hmac():
    h=auth_headers("k","s","p","GET","/api/v5/account/balance",stamp="2020-01-01T00:00:00.000Z");assert h["OK-ACCESS-SIGN"]=="3+YzNZYq3N3si/o/YkbHvC4RpV8WeOY5ZpO7abfFcYA=";assert h["x-simulated-trading"]=="1"
def test_normalizers():
    assert candle(["1","2","4","1","3","9","0","0","1"],"BTC-USDT","M1")["is_closed"]
    assert trade({"instId":"BTC-USDT","tradeId":"7","ts":"1","px":"2","sz":"3","side":"buy"})["side"]=="buy"
    assert book({"ts":"1","seqId":"2","bids":[["2","3","1"]],"asks":[["4","5","1"]]},"BTC-USDT")["sequenceId"]==2
