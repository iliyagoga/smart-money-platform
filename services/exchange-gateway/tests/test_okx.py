from src.okx import auth_headers,book,candle,trade,ws_login
import httpx
import pytest
from pydantic import ValidationError
from decimal import Decimal
from src.service import ExchangeGateway,attached_exit_orders,incremental_start,instrument_spec,okx_ack,okx_error_details,price_to_tick
from src.settings import Settings
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

def test_price_is_rounded_to_exchange_tick():
    assert price_to_tick(126.6408,.01)=="126.64"
    assert price_to_tick(130.4784,.01)=="130.48"

def test_split_take_profits_cover_entry_and_keep_one_structural_stop():
    orders,metadata=attached_exit_orders("00000000-0000-0000-0000-000000000001",
      Decimal("10"),Decimal("0.01"),.1,[110,120],[.4,.6],95)
    take_profits=[item for item in orders if "tpTriggerPx" in item]
    stops=[item for item in orders if "slTriggerPx" in item]
    assert [Decimal(item["sz"]) for item in take_profits]==[Decimal("4"),Decimal("6")]
    assert sum(Decimal(item["sz"]) for item in take_profits)==Decimal("10")
    assert len(stops)==1 and stops[0]["slTriggerPx"]=="95.0"
    assert {value["kind"] for value in metadata.values()}=={"TAKE_PROFIT","STOP_LOSS"}

def test_split_take_profit_rounding_assigns_remainder_to_last_target():
    orders,_=attached_exit_orders("00000000-0000-0000-0000-000000000001",
      Decimal("3"),Decimal("1"),.1,[110,120],[.5,.5],95)
    assert [item["sz"] for item in orders if "tpTriggerPx" in item]==["1","2"]

def test_move_to_break_even_keeps_only_full_size_final_target_and_separate_stop():
    orders,metadata=attached_exit_orders("00000000-0000-0000-0000-000000000001",
      Decimal("10"),Decimal("1"),.1,[110,120],[.5,.5],95,"AFTER_TARGET")
    targets=[item for item in orders if "tpTriggerPx" in item]
    stops=[item for item in orders if "slTriggerPx" in item]
    assert len(targets)==1 and targets[0]["tpTriggerPx"]=="120.0" and targets[0]["sz"]=="10"
    assert len(stops)==1 and {item["kind"] for item in metadata.values()}=={"TAKE_PROFIT","STOP_LOSS"}

def test_one_r_uses_separate_amendable_stop_even_with_one_target():
    orders,metadata=attached_exit_orders("00000000-0000-0000-0000-000000000001",
      Decimal("10"),Decimal("1"),.1,[120],[1],95,"ONE_R")
    assert len(orders)==2
    assert {item["kind"] for item in metadata.values()}=={"TAKE_PROFIT","STOP_LOSS"}

def test_break_even_amends_the_owned_okx_stop_and_confirms_to_execution():
    import asyncio,json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        service.db=AsyncMock();service.redis=AsyncMock();service.private=AsyncMock(
          return_value=[{"algoClOrdId":"stop-1","sCode":"0","sMsg":""}])
        service.instrument_order_spec=AsyncMock(return_value={"tick_size":.1})
        service.record_trading_log=AsyncMock()
        service.db.fetchrow.return_value={"symbol":"BTC-USDT-SWAP","execution_mode":"DEMO",
          "exit_algos":{"stop-1":{"kind":"STOP_LOSS"},"tp-1":{"kind":"TAKE_PROFIT"}}}
        payload={"id":"00000000-0000-0000-0000-000000000001",
          "order_id":"00000000-0000-0000-0000-000000000001","position_id":"position-1",
          "symbol":"BTC-USDT-SWAP","execution_mode":"DEMO","stop_loss_price":100.04,
          "trigger_kind":"ONE_R","trigger_price":105}
        result=await service.amend_protection(payload)
        path,request=service.private.await_args.args[1:]
        assert path=="/api/v5/trade/amend-algos"
        assert request["algoClOrdId"]=="stop-1" and request["newSlTriggerPx"]=="100.0"
        event=json.loads(service.redis.xadd.await_args.args[1]["data"])
        assert event["event_type"]=="exchange.protection_updated"
        assert event["payload"]["status"]=="UPDATED" and result["status"]=="UPDATED"
    asyncio.run(check())

def test_okx_ack_preserves_detailed_rejection():
    with pytest.raises(ValueError,match='"sCode":"51000"'):
        okx_ack([{"sCode":"51000","sMsg":"Parameter error","ordId":""}],"order")

def test_top_level_okx_error_preserves_nested_order_reason():
    details=okx_error_details({"code":"1","msg":"All operations failed",
      "data":[{"sCode":"51001","sMsg":"Instrument does not exist","ordId":""}]})
    assert details=={"code":"1","msg":"All operations failed","sCode":"51001","sMsg":"Instrument does not exist"}

def test_live_trading_events_are_persisted_but_paper_events_are_not():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        service.db=AsyncMock()
        live={"id":"00000000-0000-0000-0000-000000000001","symbol":"BTC-USDT-SWAP","execution_mode":"DEMO"}
        await service.record_trading_log(live,"ORDER_RECEIVED","RECEIVED",{"side":"BUY"})
        service.db.execute.assert_awaited_once()
        await service.record_trading_log({**live,"execution_mode":"PAPER"},"ORDER_RECEIVED","RECEIVED")
        assert service.db.execute.await_count==1
    asyncio.run(check())

def test_live_account_requires_net_mode_trade_only_key_and_ip_binding():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False))
        service.private=AsyncMock(return_value=[{"posMode":"net_mode","perm":"read_only,trade","ip":"203.0.113.10"}])
        assert (await service.require_safe_account_config())["posMode"]=="net_mode"
        for config,message in [
          ({"posMode":"long_short_mode","perm":"trade","ip":"203.0.113.10"},"net position"),
          ({"posMode":"net_mode","perm":"read_only","ip":"203.0.113.10"},"trade permission"),
          ({"posMode":"net_mode","perm":"trade,withdraw","ip":"203.0.113.10"},"withdraw"),
          ({"posMode":"net_mode","perm":"trade","ip":""},"server IP"),
        ]:
            service.private.return_value=[config]
            with pytest.raises(ValueError,match=message):await service.require_safe_account_config()
    asyncio.run(check())

def test_availability_reports_okx_http_failure_instead_of_raising_server_error():
    import asyncio
    from types import SimpleNamespace

    async def check():
        service=ExchangeGateway(SimpleNamespace(
          history_concurrency=1,okx_demo=False,trading_enabled=True,
          okx_api_key="key",okx_secret_key="secret",okx_passphrase="passphrase",
          okx_rest_url="https://www.okx.com"))
        service.client=httpx.AsyncClient(transport=httpx.MockTransport(
          lambda request:httpx.Response(503,text="upstream unavailable",request=request)))
        try:result=await service.instrument_availability("AAVE-USDT-SWAP","PRODUCTION")
        finally:await service.client.aclose()
        assert result["available"] is False
        assert result["reason"]=="OKX HTTP 503: upstream unavailable"
    asyncio.run(check())

@pytest.mark.parametrize("changes",[
    {"okx_rest_url":"http://www.okx.com"},
    {"okx_private_ws_url":"ws://wspap.okx.com/ws/v5/private"},
    {"okx_api_key":"key"},
    {"trading_enabled":True},
    {"margin_mode":"invalid"},
    {"history_concurrency":0},
])
def test_insecure_exchange_settings_fail_closed(changes):
    with pytest.raises(ValidationError):Settings(_env_file=None,**changes)

def test_trading_accepts_complete_credentials_over_encrypted_transports():
    configured=Settings(_env_file=None,trading_enabled=True,okx_api_key="key",
                        okx_secret_key="secret",okx_passphrase="passphrase")
    assert configured.trading_enabled
