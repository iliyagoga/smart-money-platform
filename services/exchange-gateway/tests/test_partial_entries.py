import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.service import ExchangeAmbiguousError,ExchangeGateway


ORDER_ID="76550f47-47f4-4847-b4c5-6fc7a5d2e47c"
STOP_ID="SMA76550f4747f44847b4c56fc7a5S"


def entry(state="partially_filled",quantity="1",**changes):
    return {"tag":"SMPELLIOTT","clOrdId":"SMP76550f4747f44847b4c56fc7a5d2e",
            "ordId":"4074087254419787776","instId":"ATOM-USDT-SWAP",
            "side":"sell","state":state,"sz":"2","accFillSz":quantity,
            "avgPx":"1.369","execType":"T","fillTime":"1793919661791",
            "uTime":"1793919661792",**changes}


def stop(**changes):
    return {"algoClOrdId":STOP_ID,"instId":"ATOM-USDT-SWAP","side":"buy",
            "state":"live","slTriggerPx":"1.454","sz":"2",**changes}


@pytest.fixture
def gateway():
    service=ExchangeGateway(SimpleNamespace(history_concurrency=1,okx_demo=False))
    service.db=AsyncMock();service.redis=AsyncMock()
    service.db.fetchval.return_value={STOP_ID:{"kind":"STOP_LOSS"}}
    service.cancel_order=AsyncMock();service.record_trading_log=AsyncMock()
    service.enqueue_exchange_event=AsyncMock();service.flush_exchange_event_outbox=AsyncMock()
    service.private_ready.set();service.reconciled=True
    class Connection:
        async def __aenter__(self):return self
        async def __aexit__(self,*_):return False
        def transaction(self):return self
        execute=AsyncMock()
    service.db.acquire=lambda:Connection()
    return service


def run(coroutine):
    return asyncio.run(coroutine)


def test_atom_transient_partial_is_replaced_with_confirmed_full_fill(gateway):
    gateway.private=AsyncMock(side_effect=[[entry("filled","2")],[stop()]])
    current,unprotected=run(gateway.resolve_partial_entry(entry(),ORDER_ID))
    assert current["state"]=="filled" and current["accFillSz"]=="2"
    assert not unprotected
    gateway.cancel_order.assert_not_awaited()
    assert all(call.args[0]=="GET" for call in gateway.private.await_args_list)


@pytest.mark.parametrize("terminal",["filled","canceled","partially_filled"])
@pytest.mark.parametrize("cancel_failed",[False,True])
def test_partial_cancellation_race_uses_final_cumulative_fill(gateway,terminal,cancel_failed):
    if cancel_failed:gateway.cancel_order.side_effect=ValueError("Already filled")
    final=entry(terminal,"2" if terminal=="filled" else "1")
    gateway.private=AsyncMock(side_effect=[[entry()],[final],[stop()]])
    current,unprotected=run(gateway.resolve_partial_entry(entry(),ORDER_ID))
    assert current==final
    assert unprotected==(terminal!="filled")
    gateway.cancel_order.assert_awaited_once_with(ORDER_ID)


@pytest.mark.parametrize("changes",[
    {"state":"canceled"},{"state":"effective"},{"sz":"1"},
    {"slTriggerPx":""},{"side":"sell"},{"instId":"BTC-USDT-SWAP"},
    {"algoClOrdId":"other-stop"},
])
def test_full_fill_without_matching_live_stop_still_forces_exit(gateway,changes):
    gateway.private=AsyncMock(side_effect=[[entry("filled","2")],[stop(**changes)]])
    current,unprotected=run(gateway.resolve_partial_entry(entry(),ORDER_ID))
    assert current["accFillSz"]=="2" and unprotected
    gateway.cancel_order.assert_not_awaited()


def test_close_fraction_stop_covers_entire_position(gateway):
    gateway.private=AsyncMock(side_effect=[[entry("filled","2")],[stop(sz="",closeFraction="1")]])
    assert not run(gateway.resolve_partial_entry(entry(),ORDER_ID))[1]


def test_long_entry_requires_sell_stop(gateway):
    observed=entry(side="buy")
    gateway.private=AsyncMock(side_effect=[[entry("filled","2",side="buy")],[stop(side="sell",slTriggerPx="1.2")]])
    assert not run(gateway.resolve_partial_entry(observed,ORDER_ID))[1]


@pytest.mark.parametrize("response",[
    [],ExchangeAmbiguousError("REST timeout"),[entry(quantity="0")],
    [entry(ordId="other-order")],[entry(avgPx="")],[entry(quantity="NaN")],
])
def test_unavailable_or_inconsistent_rest_preserves_fill_and_exit(gateway,response):
    gateway.private=AsyncMock(side_effect=[response])
    current,unprotected=run(gateway.resolve_partial_entry(entry(),ORDER_ID))
    assert current==entry() and unprotected
    gateway.cancel_order.assert_awaited_once_with(ORDER_ID)


@pytest.mark.parametrize("missing",[True,False])
def test_missing_stop_metadata_or_rest_failure_keeps_full_fill_for_exit(gateway,missing):
    if missing:gateway.db.fetchval.return_value={}
    gateway.private=AsyncMock(side_effect=[[entry("filled","2")],ExchangeAmbiguousError("Stop unavailable")])
    current,unprotected=run(gateway.resolve_partial_entry(entry(),ORDER_ID))
    assert current["accFillSz"]=="2" and unprotected


def test_private_atom_sequence_publishes_full_quantity_without_forced_exit(gateway):
    gateway.db.fetchrow.return_value={"local_order_id":ORDER_ID,"execution_mode":"PRODUCTION",
      "contract_value":.1,"position_exit":False,"reduce_only":False,"exit_metadata":None}
    gateway.private=AsyncMock(side_effect=[[entry("filled","2")],[stop()]])
    async def check():
        for item in [entry("live","0"),entry(),entry("filled","2")]:
            await gateway.handle_private({"arg":{"channel":"orders"},"data":[item]})
    run(check())
    events=[call.args[1]["payload"] for call in gateway.enqueue_exchange_event.await_args_list]
    assert [event["status"] for event in events]==["OPEN","FILLED","FILLED"]
    assert [event["filled_quantity"] for event in events]==[0,.2,.2]
    assert all(not event["unprotected_partial"] for event in events)
    assert events[1]["filled_price"]==1.369 and events[1]["executed_at"]==1793919661791
    assert gateway.reconciled and gateway.private_ready.is_set()
    gateway.cancel_order.assert_not_awaited()
    assert gateway.record_trading_log.await_args_list[1].args[3]["observed_exchange"]["state"]=="partially_filled"


@pytest.mark.parametrize("position_exit,reduce_only",[(True,False),(False,True)])
def test_partial_exits_are_never_cancelled_or_treated_as_entries(gateway,position_exit,reduce_only):
    gateway.db.fetchrow.return_value={"local_order_id":ORDER_ID,"execution_mode":"PRODUCTION",
      "contract_value":1,"position_exit":position_exit,"reduce_only":reduce_only,"exit_metadata":None}
    gateway.resolve_partial_entry=AsyncMock()
    run(gateway.handle_private({"arg":{"channel":"orders"},"data":[entry()]}))
    event=gateway.enqueue_exchange_event.await_args.args[1]["payload"]
    assert event["status"]=="PARTIALLY_FILLED" and not event["unprotected_partial"]
    gateway.resolve_partial_entry.assert_not_awaited();gateway.cancel_order.assert_not_awaited()


@pytest.mark.parametrize("safe",[True,False])
def test_reconciliation_uses_same_partial_entry_verification(gateway,safe):
    row={"local_order_id":ORDER_ID,"cl_ord_id":entry()["clOrdId"],
         "symbol":"ATOM-USDT-SWAP","reduce_only":False}
    gateway.db.fetch.side_effect=[[row],[],[]]
    gateway.db.fetchval.return_value=1
    gateway.private=AsyncMock(side_effect=[[entry()],[]])
    gateway.resolve_partial_entry=AsyncMock(return_value=(entry("filled","2") if safe else entry(),not safe))
    gateway.recover_protective_fills=AsyncMock(return_value=False)
    gateway.sync_account_bills=AsyncMock()
    if safe:run(gateway.reconcile_orders())
    else:
        with pytest.raises(ValueError,match="forced exit"):run(gateway.reconcile_orders())
    event=gateway.enqueue_exchange_event.await_args.args[1]["payload"]
    assert event["unprotected_partial"] is not safe
    assert gateway.reconciled is safe
    gateway.resolve_partial_entry.assert_awaited_once_with(entry(),ORDER_ID)


def test_private_unresolved_partial_cancels_before_publishing_forced_exit(gateway):
    gateway.db.fetchrow.return_value={"local_order_id":ORDER_ID,"execution_mode":"PRODUCTION",
      "contract_value":1,"position_exit":False,"reduce_only":False,"exit_metadata":None}
    gateway.private=AsyncMock(side_effect=ExchangeAmbiguousError("Timeout"))
    async def enqueue(*_):
        gateway.cancel_order.assert_awaited_once_with(ORDER_ID)
    gateway.enqueue_exchange_event.side_effect=enqueue
    run(gateway.handle_private({"arg":{"channel":"orders"},"data":[entry()]}))
    event=gateway.enqueue_exchange_event.await_args.args[1]["payload"]
    assert event["unprotected_partial"] and event["filled_quantity"]==1
    assert not gateway.reconciled and not gateway.private_ready.is_set()
