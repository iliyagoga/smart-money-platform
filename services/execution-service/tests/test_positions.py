from src.manager import PositionManager,fee_adjusted_break_even,liquidation_price
from src.service import actionable_candle
from src.models import *
from src.service import ExecutionService
import asyncio
import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock

def position(**changes):
    data=dict(order_id="o",symbol="BTC-USDT",direction="LONG",entry_price=100,current_price=100,quantity=10,initial_quantity=10,stop_loss_price=95,initial_stop_loss_price=95,take_profit_prices=[110])
    data.update(changes);return Position(**data)
def candle(low,high,close):return Candle(symbol="BTC-USDT",timeframe="M1",timestamp=1,open=100,low=low,high=high,close=close,volume=1000)

def test_only_new_m1_candles_are_used_for_execution():
    item=candle(99,101,100).model_copy(update={"timestamp":120_000})
    assert actionable_candle(item,120_001)
    assert not actionable_candle(item.model_copy(update={"timestamp":60_000}),120_000)
    assert not actionable_candle(item.model_copy(update={"timeframe":"H4"}),120_001)
def test_stop_has_conservative_priority():
    events=PositionManager().update(position(),candle(94,111,105));assert events[0][0]=="close" and events[0][1]["reason"]=="STRUCTURAL_STOP"
def test_take_profit_closes_single_target():
    events=PositionManager().update(position(),candle(99,111,110));assert events[0][0]=="close" and events[0][1]["reason"]=="FIXED_RR_TARGET"
def test_one_r_protects_position():
    p=position(take_profit_prices=[120]);events=PositionManager().update(p,candle(99,106,105));assert p.stop_loss_price==100 and p.status=="PROTECTED" and events[0][0]=="updated"
def test_move_to_break_even_target_does_not_partially_close():
    p=position(take_profit_prices=[110,120],target_allocations=[.5,.5],break_even_rule="AFTER_TARGET")
    events=PositionManager().update(p,candle(99,111,110))
    assert events[0][0]=="updated" and p.quantity==10 and p.take_profit_prices==[120]
    assert p.stop_loss_price==100 and p.status=="PROTECTED"
def test_short_stop():
    p=position(direction="SHORT",stop_loss_price=105,take_profit_prices=[90]);events=PositionManager().update(p,candle(89,106,95));assert events[0][1]["reason"]=="STRUCTURAL_STOP"

def test_initial_stop_keeps_one_r_stable_after_stop_changes():
    p=position(stop_loss_price=90,initial_stop_loss_price=95,take_profit_prices=[120])
    events=PositionManager().update(p,candle(96,106,105))
    assert events[0][0]=="updated" and p.stop_loss_price==100

def test_all_targets_reached_in_one_candle_match_backtest_sequence():
    p=position(take_profit_prices=[105,110],target_allocations=[.5,.5],break_even_rule="OFF")
    events=PositionManager().update(p,candle(99,111,110))
    assert [event[0] for event in events]==["partial","close"]
    assert [event[1]["price"] for event in events]==[105,110]

def test_fee_adjusted_break_even_and_liquidation_match_replay_math():
    p=position(entry_fee_percent=.02,taker_fee_percent=.05,slippage_percent=.1,tick_size=.01,
      leverage=10,maintenance_margin_percent=.5,liquidation_fee_percent=.5)
    assert fee_adjusted_break_even(p)==pytest.approx(100.18)
    assert liquidation_price(p)==pytest.approx((1000-100+5+.2)/(10*(1-.0055)))
def test_second_order_is_rejected_while_first_is_active():
    service=ExecutionService("postgresql://unused","redis://unused")
    first=Order(symbol="BTC-USDT",side="BUY",type="LIMIT",price=100,quantity=1,status="OPEN")
    service.orders[first.id]=first
    second=Order(symbol="ETH-USDT",side="BUY",type="LIMIT",price=100,quantity=1)
    with pytest.raises(ValueError,match="Another trade is still active"):
        asyncio.run(service.create_order(second))

def test_exchange_rejection_reason_is_preserved_on_order():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=1,status="SUBMITTING")
        service.orders[order.id]=order;service.save_order=AsyncMock();service.publish=AsyncMock()
        await service.on_exchange_order({"order_id":order.id,"status":"REJECTED","reason":"OKX sCode 51001"})
        assert order.status=="REJECTED" and order.rejection_reason=="OKX sCode 51001"
        service.publish.assert_awaited_once()
    asyncio.run(check())

def test_order_save_publishes_status_update_for_live_ui():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.db=AsyncMock();service.publish=AsyncMock()
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=1,status="SUBMITTING")
        await service.save_order(order)
        service.publish.assert_awaited_once_with("order.updated",{
          "order_id":order.id,"signal_id":None,"symbol":"BTC-USDT","status":"SUBMITTING","rejection_reason":None,
        })
    asyncio.run(check())

def test_closed_trade_updates_edited_current_capital_when_reinvesting():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.db=AsyncMock();service.publish_channel=AsyncMock()
        service.db.fetchrow.return_value={"config":{
          "initialCapital":10_000,"currentCapital":100,"elliott":{"reinvestProfits":True},
        }}
        await service.update_current_capital("BTC-USDT",25.5)
        saved=service.db.execute.await_args.args[2]
        assert '"currentCapital": 125.5' in saved
        service.publish_channel.assert_awaited_once()
    asyncio.run(check())

def test_closed_trade_updates_capital_even_when_profit_reinvestment_is_disabled():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.db=AsyncMock();service.publish_channel=AsyncMock()
        service.db.fetchrow.return_value={"config":{
          "initialCapital":10_000,"currentCapital":100,"elliott":{"reinvestProfits":False},
        }}
        await service.update_current_capital("BTC-USDT",-25.5)
        assert '"currentCapital": 74.5' in service.db.execute.await_args.args[2]
        service.publish_channel.assert_awaited_once()
    asyncio.run(check())

def test_submitting_order_also_reserves_the_trading_slot():
    service=ExecutionService("postgresql://unused","redis://unused")
    first=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=1,status="SUBMITTING")
    service.orders[first.id]=first;service.save_order=AsyncMock();service.stream=AsyncMock()
    second=Order(symbol="ETH-USDT",side="BUY",type="MARKET",price=100,quantity=1)
    with pytest.raises(ValueError,match="Another trade is still active"):
        asyncio.run(service.create_order(second))

def test_paper_market_waits_for_next_candle_and_applies_slippage():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.save_order=AsyncMock();service.stream=AsyncMock();service.fill=AsyncMock()
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=1,
                    execution_mode="PAPER",created_at=1,slippage_percent=.1)
        await service.create_order(order)
        assert order.status=="OPEN"
        service.fill.assert_not_awaited()
        await service.on_candle(candle(99,102,101).model_copy(update={"timestamp":2,"open":100}))
        service.fill.assert_awaited_once_with(order,100.1,executed_at=2)
    asyncio.run(check())

def test_expired_order_is_cancelled_and_does_not_fill():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="LIMIT",price=100,quantity=1,
                    status="OPEN",created_at=1,expires_at=10)
        service.orders[order.id]=order;service.request_cancel=AsyncMock();service.fill=AsyncMock()
        await service.on_candle(candle(99,101,100).model_copy(update={"timestamp":11}))
        service.request_cancel.assert_awaited_once_with(order)
        service.fill.assert_not_awaited()
    asyncio.run(check())

def test_paper_fill_is_capped_by_candle_volume_and_rounded_to_lot():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.save_order=AsyncMock();service.stream=AsyncMock();service.fill=AsyncMock()
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=10,
          execution_mode="PAPER",created_at=1,volume_participation_percent=5,lot_size=.1)
        await service.create_order(order)
        await service.on_candle(candle(99,101,100).model_copy(update={"timestamp":2,"volume":23}))
        assert order.quantity==1.1
        service.fill.assert_awaited_once()
    asyncio.run(check())

def test_partial_take_uses_the_same_entry_and_exit_fees_as_backtest():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        service.save_position=AsyncMock();service.publish=AsyncMock()
        p=position(entry_fee_percent=.02,maker_fee_percent=.02)
        _,remaining,pnl=await service.close(p,5,110,"FIXED_RR_TARGET")
        assert remaining==5
        assert p.fees==pytest.approx(.21)
        assert pnl==pytest.approx(49.79)
    asyncio.run(check())

def test_exchange_partial_fills_use_cumulative_quantity_and_incremental_price():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=10,status="SUBMITTING")
        service.orders[order.id]=order;service.fill=AsyncMock()
        await service.on_exchange_order({"order_id":order.id,"status":"PARTIALLY_FILLED",
          "filled_price":100,"filled_quantity":4})
        order.filled_quantity=4;order.filled_price=100
        await service.on_exchange_order({"order_id":order.id,"status":"FILLED",
          "filled_price":103,"filled_quantity":10})
        assert service.fill.await_args_list[0].args[1]==100
        assert service.fill.await_args_list[1].args[1]==pytest.approx(105)
        assert service.fill.await_args_list[1].kwargs=={"cumulative_quantity":10,"final":True}
    asyncio.run(check())

def test_each_live_take_profit_and_stop_tracks_its_own_cumulative_fill():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="LIMIT",price=100,quantity=10,status="FILLED")
        p=position(order_id=order.id,take_profit_prices=[110,120],target_allocations=[.5,.5],execution_mode="DEMO")
        service.orders[order.id]=order;service.positions[p.id]=p;service.close=AsyncMock()
        await service.on_exchange_order({"order_id":order.id,"position_exit":True,"protective_id":"tp-1",
          "protective_kind":"TAKE_PROFIT","target_price":110,"status":"FILLED","filled_price":110,"filled_quantity":5})
        await service.on_exchange_order({"order_id":order.id,"position_exit":True,"protective_id":"tp-2",
          "protective_kind":"TAKE_PROFIT","target_price":120,"status":"FILLED","filled_price":120,"filled_quantity":5})
        await service.on_exchange_order({"order_id":order.id,"position_exit":True,"protective_id":"sl",
          "protective_kind":"STOP_LOSS","status":"FILLED","filled_price":95,"filled_quantity":5})
        assert [call.args[1] for call in service.close.await_args_list]==[5,5,5]
        assert [call.args[3] for call in service.close.await_args_list]==[
          "FIXED_RR_TARGET","FIXED_RR_TARGET","STRUCTURAL_STOP"]
        assert p.take_profit_prices==[] and p.targets_hit==2
    asyncio.run(check())

def test_live_candles_only_mark_positions_and_do_not_close_them_locally():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        p=position(execution_mode="DEMO",opened_at=1)
        service.positions[p.id]=p;service.save_position=AsyncMock();service.publish=AsyncMock();service.close=AsyncMock()
        await service.on_candle(candle(94,111,105).model_copy(update={"timestamp":2}))
        service.close.assert_not_awaited();assert p.current_price==105
        service.save_position.assert_awaited_once()
    asyncio.run(check())

@pytest.mark.parametrize("entry_model",[
    "CHOCH_MARKET","CHOCH_RETRACE","WAVE1_BREAK_RETRACE","WAVE1_BREAK_MARKET",
    "WAVE1_BREAK_STOP","WAVE1_BREAK_RETEST_CONFIRM","MICRO_WAVE3","DISPLACEMENT_RETRACE",
    "P2_LIQUIDITY_SWEEP","WAVE2_TRENDLINE_BREAK","ADX_ACCELERATION",
    "VOLATILITY_EXPANSION","VOLUME_EXPANSION",
])
def test_live_config_accepts_every_backtest_entry_model(entry_model):
    config={"elliott":{"entryModel":entry_model,"takeProfitCount":2,
      "firstTakeAction":"MOVE_TO_BREAK_EVEN","breakEvenAtOneR":True}}
    ExecutionService.validate_live_config(config,"DEMO")
    ExecutionService.validate_live_config(config,"PRODUCTION")

def test_live_one_r_requests_exchange_stop_amendment_and_waits_for_confirmation():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="MARKET",price=100,quantity=10,status="FILLED")
        p=position(order_id=order.id,take_profit_prices=[120],execution_mode="DEMO",opened_at=1,
                   break_even_rule="ONE_R")
        service.orders[order.id]=order;service.positions[p.id]=p
        service.save_position=AsyncMock();service.publish=AsyncMock();service.stream=AsyncMock()
        await service.on_candle(candle(99,106,105).model_copy(update={"timestamp":2}))
        service.stream.assert_awaited_once()
        event,payload=service.stream.await_args.args
        assert event=="position.protection_requested" and payload["stop_loss_price"]==100
        assert p.protection_pending and not p.protected
        await service.on_protection_updated({**payload,"status":"UPDATED"})
        assert p.protected and not p.protection_pending and p.status=="PROTECTED"
    asyncio.run(check())

def test_live_move_to_break_even_removes_first_target_only_after_exchange_confirmation():
    async def check():
        service=ExecutionService("postgresql://unused","redis://unused")
        order=Order(symbol="BTC-USDT",side="BUY",type="LIMIT",price=100,quantity=10,status="FILLED")
        p=position(order_id=order.id,take_profit_prices=[110,120],target_allocations=[.5,.5],
                   execution_mode="DEMO",opened_at=1,break_even_rule="AFTER_TARGET")
        service.orders[order.id]=order;service.positions[p.id]=p
        service.save_position=AsyncMock();service.publish=AsyncMock();service.stream=AsyncMock()
        await service.on_candle(candle(99,111,110).model_copy(update={"timestamp":2}))
        payload=service.stream.await_args.args[1]
        assert p.take_profit_prices==[110,120]
        await service.on_protection_updated({**payload,"status":"UPDATED"})
        assert p.take_profit_prices==[120] and p.target_allocations==[.5] and p.targets_hit==1
        assert p.quantity==10
    asyncio.run(check())

def test_manual_close_payload_cannot_spoof_exit_price_or_reason():
    with pytest.raises(ValidationError):CloseRequest(price=1)
    with pytest.raises(ValidationError):CloseRequest(reason="FIXED_RR_TARGET")
