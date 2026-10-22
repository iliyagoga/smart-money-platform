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
    from unittest.mock import AsyncMock,Mock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        service.db=AsyncMock();service.redis=AsyncMock();service.private=AsyncMock(
          return_value=[{"algoClOrdId":"stop-1","sCode":"0","sMsg":""}])
        service.trading_instrument_spec=AsyncMock(return_value={"tick_size":.1})
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

def test_production_order_converts_base_quantity_to_okx_contracts_with_protection():
    import asyncio,json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False,margin_mode="cross"))
        service.db=AsyncMock();service.redis=AsyncMock();service.record_trading_log=AsyncMock()
        service.private_ready.set();service.reconciled=True
        service.db.fetchrow.side_effect=[None,{"mode":"PRODUCTION","config":{}},{"mode":"PRODUCTION","config":{}},
                                         {"local_order_id":"00000000-0000-0000-0000-000000000001"}]
        service.require_safe_account_config=AsyncMock(return_value={"posMode":"net_mode"})
        service.instrument_order_spec=AsyncMock(return_value={"validation_status":"ACTIVE"})
        service.trading_instrument_spec=AsyncMock(return_value={
          "contract_value":.01,"lot_size":.0001,"minimum_order_size":.0001,"tick_size":.1,
        })
        service.private=AsyncMock(side_effect=[[],[{"ordId":"okx-order-1","sCode":"0","sMsg":""}]])
        payload={
          "id":"00000000-0000-0000-0000-000000000001","symbol":"BTC-USDT-SWAP",
          "execution_mode":"PRODUCTION","side":"BUY","type":"MARKET","quantity":.84,
          "leverage":1,"margin_mode":"cross","stop_loss_price":99,
          "take_profit_prices":[102,103],"target_allocations":[.5,.5],"break_even_rule":"OFF",
        }
        result=await service.place_order(payload)
        assert result=={"order_id":payload["id"],"exchange_order_id":"okx-order-1","status":"ACCEPTED"}
        order_call=service.private.await_args_list[1]
        assert order_call.args[0:2]==("POST","/api/v5/trade/order")
        request=order_call.args[2]
        assert request["instId"]=="BTC-USDT-SWAP" and request["tdMode"]=="cross"
        assert request["side"]=="buy" and request["ordType"]=="market"
        assert Decimal(request["sz"])==Decimal("84")
        assert len(request["attachAlgoOrds"])==3
        event=json.loads(service.redis.xadd.await_args.args[1]["data"])
        assert event["event_type"]=="exchange.order_updated"
        assert event["payload"]["exchange_order_id"]=="okx-order-1"
    asyncio.run(check())

def test_reduce_only_exit_remains_available_after_asset_is_disabled():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False,margin_mode="cross"))
        service.db=AsyncMock();service.redis=AsyncMock();service.record_trading_log=AsyncMock()
        service.private_subscribed=True
        service.db.fetchrow.side_effect=[None,{"local_order_id":"00000000-0000-0000-0000-000000000002"}]
        service.require_safe_account_config=AsyncMock(return_value={"posMode":"net_mode"})
        service.instrument_order_spec=AsyncMock(side_effect=AssertionError("disabled asset rejected exit"))
        service.trading_instrument_spec=AsyncMock(return_value={
          "contract_value":.01,"lot_size":.0001,"minimum_order_size":.0001,"tick_size":.1,
        })
        service.private=AsyncMock(return_value=[{"ordId":"exit-1","sCode":"0","sMsg":""}])
        payload={"id":"00000000-0000-0000-0000-000000000002","symbol":"BTC-USDT-SWAP",
                 "execution_mode":"PRODUCTION","side":"SELL","type":"MARKET","quantity":.1,
                 "reduce_only":True,"leverage":1}
        result=await service.place_order(payload)
        assert result["status"]=="ACCEPTED"
        service.instrument_order_spec.assert_not_awaited()
        request=service.private.await_args.args[2]
        assert request["reduceOnly"] is True
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

def test_production_account_capacity_returns_usdt_equity_for_portfolio_preflight():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False,trading_enabled=True))
        service.require_safe_account_config=AsyncMock(return_value={"posMode":"net_mode"})
        service.private=AsyncMock(return_value=[{"details":[{
          "ccy":"USDT","eq":"140","availEq":"139.5","availBal":"139.4",
        }]}])
        result=await service.account_capacity("PRODUCTION")
        assert result=={"mode":"PRODUCTION","currency":"USDT","equity":140.0,"available":139.5}
        service.private.assert_awaited_once_with("GET","/api/v5/account/balance?ccy=USDT")
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
        service.private_ready.set();service.reconciled=True
        try:result=await service.instrument_availability("AAVE-USDT-SWAP","PRODUCTION")
        finally:await service.client.aclose()
        assert result["available"] is False
        assert result["reason"]=="OKX HTTP 503: upstream unavailable"
    asyncio.run(check())

def test_prepare_instruments_registers_and_reenables_portfolio_symbols():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock,Mock

    async def check():
        service=ExchangeGateway(SimpleNamespace(
          history_concurrency=1,symbols="BTC-USDT-SWAP",okx_rest_url="https://www.okx.com"))
        service.db=AsyncMock();service.websockets={};service.client=AsyncMock()
        response=Mock();response.json.return_value={"code":"0","data":[{
          "instId":"AVAX-USDT-SWAP","uly":"AVAX-USDT","tickSz":"0.01","lotSz":"1","minSz":"1",
          "ctVal":"0.1","state":"live",
        }]}
        service.client.get.return_value=response
        service.db.fetch.return_value=[{"symbol":"AVAX-USDT-SWAP"},{"symbol":"BTC-USDT-SWAP"}]
        result=await service.prepare_instruments(["avax-usdt-swap","AVAX-USDT-SWAP","MISSING-USDT-SWAP"])
        assert result=={"prepared":["AVAX-USDT-SWAP"],"unavailable":["MISSING-USDT-SWAP"]}
        service.db.executemany.assert_awaited_once()
        assert [item[0] for item in service.db.executemany.await_args.args[1]]==["AVAX-USDT-SWAP"]
        assert service.client.get.await_count==3  # discovery, instrument details, funding metadata
        assert service.active_symbols==["AVAX-USDT-SWAP","BTC-USDT-SWAP"]
    asyncio.run(check())

def test_instrument_metadata_remains_usable_when_funding_endpoint_fails():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock,Mock

    async def check():
        service=ExchangeGateway(SimpleNamespace(
          history_concurrency=1,okx_rest_url="https://www.okx.com",
          okx_api_key="",okx_secret_key="",okx_passphrase=""))
        service.db=AsyncMock();service.client=AsyncMock()
        instrument=Mock();instrument.json.return_value={"code":"0","data":[{
          "instId":"AVAX-USDT-SWAP","tickSz":"0.01","lotSz":"1","minSz":"1","ctVal":"0.1",
          "state":"live",
        }]}
        funding=Mock();funding.raise_for_status.side_effect=RuntimeError("funding unavailable")
        service.client.get.side_effect=[instrument,funding]
        assert await service.refresh_instrument_specs(["AVAX-USDT-SWAP"])==["AVAX-USDT-SWAP"]
        service.db.execute.assert_awaited_once()
        assert service.db.execute.await_args.args[1]=="AVAX-USDT-SWAP"
    asyncio.run(check())

def test_history_request_retries_okx_rate_limit_with_shared_throttle():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock,Mock,patch

    async def check():
        service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_rest_url="https://www.okx.com"))
        service.client=AsyncMock();service.history_request_interval=0
        limited=Mock();limited.json.return_value={"code":"50011","msg":"Rate limit reached","data":[]}
        success=Mock();success.json.return_value={"code":"0","msg":"","data":[["1","1","1","1","1","0","0","0","1"]]}
        service.client.get.side_effect=[limited,success]
        with patch("src.service.asyncio.sleep",new=AsyncMock()) as sleep:
            result=await service.history_candles_request({"instId":"BTC-USDT-SWAP","bar":"1m","limit":300})
        assert result["code"]=="0" and service.client.get.await_count==2
        sleep.assert_awaited_once_with(.5)
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
                        okx_secret_key="secret",okx_passphrase="passphrase",market_data_enabled=True)
    assert configured.trading_enabled

def test_private_websocket_endpoint_follows_account_mode():
    demo=Settings(_env_file=None,okx_demo=True,okx_private_ws_url="")
    production=Settings(_env_file=None,okx_demo=False,okx_private_ws_url="")
    assert demo.okx_private_ws_url=="wss://wspap.okx.com/ws/v5/private"
    assert production.okx_private_ws_url=="wss://ws.okx.com/ws/v5/private"
    with pytest.raises(ValidationError,match="OKX_PRIVATE_WS_URL"):
        Settings(_env_file=None,okx_demo=False,okx_private_ws_url=demo.okx_private_ws_url)

def test_market_readiness_requires_fresh_m1_for_each_active_symbol():
    from time import monotonic
    from types import SimpleNamespace

    gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1,symbols="BTC-USDT-SWAP,ETH-USDT-SWAP"))
    gateway.connected["business"]=True
    gateway.last_m1_by_symbol["BTC-USDT-SWAP"]=monotonic()
    assert gateway.market_data_ready_for("BTC-USDT-SWAP")
    assert not gateway.market_data_ready_for("ETH-USDT-SWAP")
    assert not gateway.market_data_ready
    gateway.last_m1_by_symbol["ETH-USDT-SWAP"]=monotonic()
    assert gateway.market_data_ready

def test_duplicate_local_order_never_sends_second_rest_order():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False))
        gateway.db=AsyncMock();gateway.record_trading_log=AsyncMock()
        gateway.private_ready.set();gateway.reconciled=True
        gateway.db.fetchrow.return_value={"status":"UNKNOWN","exchange_order_id":None}
        gateway.private=AsyncMock()
        result=await gateway.place_order({"id":"00000000-0000-0000-0000-000000000001",
          "execution_mode":"PRODUCTION","symbol":"BTC-USDT-SWAP"})
        assert result["status"]=="UNKNOWN"
        gateway.private.assert_not_awaited()
    asyncio.run(check())

def test_concurrent_order_claim_does_not_send_second_rest_order():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False,margin_mode="cross"))
        gateway.db=AsyncMock();gateway.record_trading_log=AsyncMock()
        gateway.private_ready.set();gateway.reconciled=True
        gateway.db.fetchrow.side_effect=[None,{"mode":"PRODUCTION","config":{}},
          {"mode":"PRODUCTION","config":{}},None,{"status":"SUBMITTING","exchange_order_id":None}]
        gateway.require_safe_account_config=AsyncMock(return_value={"posMode":"net_mode"})
        gateway.instrument_order_spec=AsyncMock(return_value={"validation_status":"ACTIVE"})
        gateway.trading_instrument_spec=AsyncMock(return_value={
          "contract_value":.01,"lot_size":.0001,"minimum_order_size":.0001,"tick_size":.1})
        gateway.private=AsyncMock(return_value=[])
        result=await gateway.place_order({"id":"00000000-0000-0000-0000-000000000003",
          "execution_mode":"PRODUCTION","symbol":"BTC-USDT-SWAP","side":"BUY",
          "type":"MARKET","quantity":.1})
        assert result["status"]=="SUBMITTING"
        assert all(call.args[1]!="/api/v5/trade/order" for call in gateway.private.await_args_list)
    asyncio.run(check())

def test_new_live_order_waits_for_private_channel_before_any_rest_call():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from src.service import TradingNotReadyError

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False))
        gateway.record_trading_log=AsyncMock();gateway.private=AsyncMock()
        with pytest.raises(TradingNotReadyError,match="private orders channel"):
            await gateway.place_order({"id":"00000000-0000-0000-0000-000000000001",
              "execution_mode":"PRODUCTION","symbol":"BTC-USDT-SWAP"})
        gateway.private.assert_not_awaited()
    asyncio.run(check())

def test_reconciliation_blocks_unmanaged_exchange_exposure():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        gateway.db=AsyncMock();gateway.db.fetch.return_value=[]
        gateway.db.fetchval.side_effect=[True,1,False]
        gateway.private=AsyncMock(return_value=[{"instId":"BTC-USDT-SWAP","pos":"1"}])
        with pytest.raises(ValueError,match="Unmanaged OKX position"):
            await gateway.reconcile_orders()
        assert not gateway.reconciled and not gateway.private_ready.is_set()
    asyncio.run(check())

def test_reconciliation_replays_missed_protective_fill_from_okx():
    import asyncio,json
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        gateway.db=AsyncMock();gateway.redis=AsyncMock()
        gateway.db.fetch.return_value=[{"data":{"order_id":"00000000-0000-0000-0000-000000000001",
          "protective_filled_quantities":{}},"local_order_id":"00000000-0000-0000-0000-000000000001",
          "symbol":"BTC-USDT-SWAP","contract_value":.01,
          "exit_algos":{"stop-1":{"kind":"STOP_LOSS"}}}]
        gateway.private=AsyncMock(side_effect=[
          [{"state":"effective","ordId":"okx-exit-1"}],
          [{"state":"filled","accFillSz":"10","avgPx":"95"}],
        ])
        assert await gateway.recover_protective_fills()
        event=json.loads(gateway.redis.xadd.await_args.args[1]["data"])
        assert event["payload"]["position_exit"] is True
        assert event["payload"]["filled_quantity"]==.1
        assert event["payload"]["protective_kind"]=="STOP_LOSS"
    asyncio.run(check())

def test_backend_schedules_missing_entry_timeframe_history():
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def check():
        gateway=ExchangeGateway(SimpleNamespace(history_concurrency=1))
        gateway.db=AsyncMock();gateway.db.fetch.side_effect=[
          [{"symbol":"BTC-USDT-SWAP","config":{"elliott":{"entryTimeframe":"M30",
            "structureTimeframe":"H1","macroTimeframe":"H4"}}}],
          [],
        ]
        gateway.db.fetchval.return_value=False
        gateway.create_history=AsyncMock()
        await gateway.ensure_active_history()
        args=gateway.create_history.await_args.args
        assert set(args[2])=={"M1","M30","H1","H4"}
        assert gateway.create_history.await_args.kwargs=={"auto":True}
    asyncio.run(check())
