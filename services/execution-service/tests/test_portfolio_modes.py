import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from src.models import Order,Position
from src.service import ExecutionService


def order(symbol="ETH-USDT-SWAP",capital_mode="ALLOCATED",**kwargs):
    return Order(symbol=symbol,side="BUY",type="MARKET",quantity=1,portfolio_id="portfolio",
      portfolio_capital_mode=capital_mode,**kwargs)


def position(symbol="AVAX-USDT-SWAP",capital_mode="ALLOCATED"):
    return Position(order_id="entry",symbol=symbol,direction="LONG",entry_price=100,
      current_price=100,quantity=1,initial_quantity=1,portfolio_capital_mode=capital_mode)


def service():
    item=ExecutionService("unused","unused")
    item.save_order=AsyncMock();item.stream=AsyncMock()
    return item


@pytest.mark.parametrize("status",["PENDING","OPEN","SUBMITTING","PARTIALLY_FILLED","CANCEL_REQUESTED","UNKNOWN"])
def test_parallel_pending_orders_block_only_their_own_asset(status):
    async def check():
        item=service();first=order("AVAX-USDT-SWAP",status=status);item.orders[first.id]=first
        second=order();await item.create_order(second)
        assert second.status=="OPEN"
        with pytest.raises(ValueError,match="Another trade is still active"):
            await item.create_order(order("AVAX-USDT-SWAP"))
    asyncio.run(check())


@pytest.mark.parametrize("mode",["PAPER","DEMO","PRODUCTION"])
def test_parallel_open_position_allows_other_assets_but_rejects_its_own(mode):
    async def check():
        item=service();p=position();item.positions[p.id]=p
        candidate=order(execution_mode=mode);await item.create_order(candidate)
        assert candidate.status==("OPEN" if mode=="PAPER" else "SUBMITTING")
        if mode!="PAPER":assert item.stream.await_args.args[0]=="order.request"
        before=item.stream.await_count
        with pytest.raises(ValueError,match="Another trade is still active"):
            await item.create_order(order("AVAX-USDT-SWAP",execution_mode=mode))
        assert item.stream.await_count==before
    asyncio.run(check())


@pytest.mark.parametrize("candidate_mode,existing_mode",[
    ("SEQUENTIAL","ALLOCATED"),("ALLOCATED","SEQUENTIAL"),("SEQUENTIAL","SEQUENTIAL"),
])
def test_sequential_and_legacy_positions_keep_a_global_slot(candidate_mode,existing_mode):
    async def check():
        item=service();p=position(capital_mode=existing_mode);item.positions[p.id]=p
        with pytest.raises(ValueError,match="Another trade is still active"):
            await item.create_order(order(capital_mode=candidate_mode))
        item.stream.assert_not_awaited()
        legacy=p.model_dump();legacy.pop("portfolio_capital_mode")
        assert Position.model_validate(legacy).portfolio_capital_mode=="SEQUENTIAL"
    asyncio.run(check())


def test_restart_preserves_parallel_slots_and_closed_positions_release_only_their_asset():
    async def check():
        item=service();avax=position();eth=position("ETH-USDT-SWAP")
        item.positions={p.id:Position.model_validate_json(p.model_dump_json()) for p in (avax,eth)}
        item.positions[avax.id].status="CLOSED"
        await item.create_order(order("AVAX-USDT-SWAP"))
        with pytest.raises(ValueError,match="Another trade is still active"):
            await item.create_order(order())
        legacy=order().model_dump();legacy.pop("portfolio_capital_mode")
        assert Order.model_validate(legacy).portfolio_capital_mode=="SEQUENTIAL"
    asyncio.run(check())


def test_parallel_profit_changes_only_the_assets_allocated_capital():
    async def check():
        item=service();item.db=AsyncMock();item.publish_channel=AsyncMock()
        item.db.fetchrow.return_value={"config":{"initialCapital":84,"currentCapital":84,
          "portfolioId":"portfolio","portfolioCapitalMode":"ALLOCATED","portfolioAllocationPercent":60}}
        await item.update_current_capital("AVAX-USDT-SWAP",5.5)
        item.db.fetch.assert_not_awaited()
        item.db.execute.assert_awaited_once()
        call=item.db.execute.await_args
        assert call.args[1]=="AVAX-USDT-SWAP" and json.loads(call.args[2])["currentCapital"]==89.5
    asyncio.run(check())


def test_fill_keeps_the_portfolio_mode_on_the_persisted_position():
    async def check():
        item=service();item.db=AsyncMock();item.redis=AsyncMock()
        item.save_position=AsyncMock();item.publish=AsyncMock()
        entry=order();await item.fill(entry,100)
        p=next(iter(item.positions.values()))
        assert p.portfolio_capital_mode=="ALLOCATED"
        assert Position.model_validate_json(p.model_dump_json()).portfolio_capital_mode=="ALLOCATED"
    asyncio.run(check())


@pytest.mark.parametrize("payload_mode,calls",[("ALLOCATED",1),("SEQUENTIAL",0)])
def test_approval_keeps_the_live_mode_and_rejects_a_stale_mode(payload_mode,calls):
    async def check():
        from uuid import uuid4
        item=service();item.db=AsyncMock();item.create_order=AsyncMock()
        item.db.fetchrow.return_value={"data":{"symbol":"ETH-USDT-SWAP","direction":"LONG",
          "entry_type":"MARKET","entry_price":100,"stop_loss_price":99,"take_profit_prices":[102]},
          "config":{"portfolioCapitalMode":"ALLOCATED","portfolioId":"portfolio","elliott":{}},
          "mode":"PRODUCTION","tick_size":.01,"lot_size":.01,"minimum_order_size":.01,
          "maker_fee_rate":None,"taker_fee_rate":None,"funding_rate":None}
        await item.on_approved({"signal_id":str(uuid4()),"position_size":1,"portfolio_capital_mode":payload_mode})
        assert item.create_order.await_count==calls
        if calls:assert item.create_order.await_args.args[0].portfolio_capital_mode=="ALLOCATED"
    asyncio.run(check())


@pytest.mark.parametrize("capital_mode",["ALLOCATED","SEQUENTIAL"])
@pytest.mark.parametrize("config_key",["portfolioCapitalMode","portfolio_capital_mode"])
def test_approval_preserves_capital_mode_and_rejects_a_changed_mode(capital_mode,config_key):
    async def check():
        item=service();item.db=AsyncMock();item.create_order=AsyncMock()
        config={config_key:capital_mode,"portfolioId":"portfolio"}
        item.db.fetchrow.return_value={"data":{
          "symbol":"ETH-USDT-SWAP","direction":"LONG","entry_type":"MARKET",
          "entry_price":100,"stop_loss_price":99,"take_profit_prices":[102],
        },"config":config,"mode":"PRODUCTION","tick_size":.01,"lot_size":.01,
          "minimum_order_size":.01,"maker_fee_rate":0,"taker_fee_rate":.0005,"funding_rate":0}
        payload={"signal_id":"signal","position_size":1,"portfolio_id":"portfolio",
                 "execution_mode":"PRODUCTION","portfolio_capital_mode":capital_mode}
        await item.on_approved(payload)
        entry=item.create_order.await_args.args[0]
        assert entry.portfolio_capital_mode==capital_mode
        assert entry.execution_mode=="PRODUCTION" and entry.quantity==1
        item.create_order.reset_mock()
        config[config_key]="SEQUENTIAL" if capital_mode=="ALLOCATED" else "ALLOCATED"
        await item.on_approved(payload)
        item.create_order.assert_not_awaited()
    asyncio.run(check())
