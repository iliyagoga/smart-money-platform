import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from src.preflight import asset_preflight
from src.service import ExecutionService


def config(**changes):
    return {"currentCapital":100,"portfolioAllocationPercent":50,
            "riskPerTradePercent":1,"leverage":10,"elliott":{},**changes}


def spec(**changes):
    return {"price":10,"lot_size":1,"minimum_order_size":1,
            "contract_value":.1,"tick_size":.01,**changes}


@pytest.mark.parametrize("mode,capital",[("ALLOCATED",50),("SEQUENTIAL",100)])
def test_asset_budget_applies_allocation_once_and_preserves_config(mode,capital):
    settings=config(currentCapital=capital,portfolioCapitalMode=mode)
    original=dict(settings)
    report=asset_preflight("COIN",settings,spec(),{},100)
    assert report["valid"]
    assert report["budget"]==50 and report["risk_budget"]==.5
    assert report["minimum_quantity"]==2 and report["take_quantities"]==[1,1]
    assert report["minimum_contracts"]==20 and report["required_margin"]==20
    assert report["max_stop_distance"]==.25 and report["max_stop_percent"]==2.5
    assert settings==original


@pytest.mark.parametrize("allocations,minimum,lots,takes",[
    ([.5,.5],1,2,[1,1]),([.1,.9],1,10,[1,9]),
    ([.9,.1],1,2,[1,1]),([.4,.6],2,5,[2,3]),
    ([.9,.1],2,11,[9,2]),
])
def test_minimum_position_matches_floor_and_last_target_remainder(allocations,minimum,lots,takes):
    report=asset_preflight("COIN",config(elliott={"takeProfitAllocations":allocations}),
                           spec(minimum_order_size=minimum),{},1000)
    assert report["minimum_quantity"]==lots and report["take_quantities"]==takes
    # Every smaller integer position fails the entry or one of the exits.
    a=Decimal(str(allocations[0]))
    for quantity in range(1,lots):
        first=int(Decimal(quantity)*a)
        assert quantity<minimum or first<minimum or quantity-first<minimum


def test_insufficient_budget_blocks_without_increasing_size_or_risk():
    report=asset_preflight("COIN",config(currentCapital=10),spec(),{},100)
    assert not report["valid"] and report["budget"]==5
    assert report["minimum_quantity"]==2 and report["required_margin"]==20
    assert report["risk_percent"]==1


@pytest.mark.parametrize("requested,effective",[(0,.5),(3,.5),(.1,.1)])
def test_risk_and_margin_respect_system_limits_and_account_capacity(requested,effective):
    report=asset_preflight("COIN",config(riskPerTradePercent=requested,elliott={"useMargin":True}),
                           spec(),{"max_risk_per_trade_percent":.5,"leverage":2},40)
    assert report["risk_percent"]==effective
    assert report["budget"]==20 and report["leverage"]==2
    assert report["required_margin"]==10


def test_too_small_risk_for_a_tick_blocks_start():
    report=asset_preflight("COIN",config(riskPerTradePercent=.001),spec(),{},100)
    assert not report["valid"] and "шаг цены" in report["errors"][0]


@pytest.mark.parametrize("elliott",[
    {"takeProfitCount":1}, {"firstTakeAction":"MOVE_TO_BREAK_EVEN"},
    {"take_profit_count":1}, {"first_take_action":"MOVE_TO_BREAK_EVEN"},
])
def test_single_exit_and_break_even_action_need_only_one_exit_lot(elliott):
    report=asset_preflight("COIN",config(elliott=elliott),spec(),{},100)
    assert report["minimum_quantity"]==1 and report["take_quantities"]==[1]


def test_subcoin_contracts_and_exchange_minimum_are_not_confused():
    report=asset_preflight("BTC",config(),spec(lot_size=.0001,minimum_order_size=.0002,
                           contract_value=.01,price=10000),{},100)
    assert report["minimum_quantity"]==.0004
    assert report["minimum_contracts"]==.04
    assert report["take_quantities"]==[.0002,.0002]


def test_one_r_override_keeps_split_targets_like_live_gateway():
    report=asset_preflight("COIN",config(elliott={"firstTakeAction":"MOVE_TO_BREAK_EVEN",
                           "breakEvenAtOneR":True}),spec(),{},100)
    assert report["minimum_quantity"]==2 and report["take_quantities"]==[1,1]


@pytest.mark.parametrize("available",[0,-1,float("nan"),float("inf"),50])
def test_portfolio_capital_checks_available_funds_not_only_equity(available):
    async def check():
        service=ExecutionService("unused","unused");service.http=AsyncMock()
        # Use a mock response to exercise non-finite provider values too.
        from unittest.mock import Mock
        response=Mock();response.json.return_value={"equity":100,"available":available}
        service.http.get.return_value=response
        with pytest.raises(ValueError,match="available"):
            await service.validate_portfolio_capital("PRODUCTION",100,require_available=True)
    asyncio.run(check())


def test_missing_price_blocks_and_reports_all_assets_without_writes():
    async def check():
        service=ExecutionService("unused","unused");service.db=AsyncMock();service.redis=AsyncMock()
        service.redis.get.return_value=None
        service.db.fetch.return_value=[{"symbol":"GOOD",**spec()}, {"symbol":"STALE",**spec(price=None)}]
        result=await service.validate_portfolio_orders([("GOOD",config()),("STALE",config())],
                                                      "PRODUCTION",{"available":100})
        assert not result["valid"]
        assert result["assets"][0]["valid"]
        assert not result["assets"][1]["valid"] and "свежей цены" in result["assets"][1]["errors"][0]
        assert "5 minutes" in service.db.fetch.await_args.args[0]
        service.db.execute.assert_not_awaited()
    asyncio.run(check())
