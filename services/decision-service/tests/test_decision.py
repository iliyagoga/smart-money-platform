from src.models import *
from src.resolver import ConflictResolver
from src.risk import RiskManager

def scenario(id,direction,confidence):return Scenario(id=id,symbol="BTC-USDT",timeframe="M15",direction=direction,setup_type="TEST",confidence=confidence,entry_zone_low=99,entry_zone_high=101,stop_loss_price=95,take_profit_prices=[110],expires_at=9999999999999)
def test_conflict_rejects_inconclusive_directions():
    selected,rejected=ConflictResolver().select([scenario("a","LONG",.7),scenario("b","SHORT",.65)])
    assert selected is None and len(rejected)==2
def test_conflict_selects_clear_winner():
    selected,_=ConflictResolver().select([scenario("a","LONG",.8),scenario("b","SHORT",.65)])
    assert selected.id=="a"
def test_risk_position_size():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));decision=RiskManager().calculate(signal,10000,RiskConfig())
    assert decision.approved and decision.risk_amount==100 and decision.position_size==20
def test_strategy_risk_and_capital_capacity_match_backtest_sizing():
    signal=ConflictResolver().signal(scenario("a","LONG",1)).model_copy(update={"entry_price":100,"stop_loss_price":90})
    cash=RiskManager().calculate(signal,10000,RiskConfig(),risk_percent_override=0,
      allocation_percent=50,use_margin=False,lot_size=.1)
    margin=RiskManager().calculate(signal,10000,RiskConfig(),risk_percent_override=50,
      allocation_percent=25,use_margin=True,leverage_override=2,lot_size=.1)
    assert cash.approved and cash.position_size==50 and cash.leverage==1
    assert margin.approved and margin.position_size==50 and margin.leverage==2
def test_strategy_sizing_respects_lot_and_exchange_minimum():
    signal=ConflictResolver().signal(scenario("a","LONG",1)).model_copy(update={"entry_price":100,"stop_loss_price":99})
    decision=RiskManager().calculate(signal,100,RiskConfig(min_position_size=.0001),
      risk_percent_override=1,use_margin=False,lot_size=.1,minimum_order_size=2)
    assert not decision.approved and decision.position_size==1
def test_disabled_reinvestment_caps_sizing_capital_at_initial_balance():
    signal=ConflictResolver().signal(scenario("a","LONG",1)).model_copy(update={"entry_price":100,"stop_loss_price":90})
    decision=RiskManager().calculate(signal,20000,RiskConfig(),risk_percent_override=0,
      allocation_percent=100,use_margin=False,capital_ceiling=10000)
    assert decision.approved and decision.position_size==100
def test_signal_preserves_scenario_entry_type():
    item=scenario("market","LONG",.7).model_copy(update={"entry_type":"MARKET"})
    assert ConflictResolver().signal(item).entry_type=="MARKET"
def test_daily_loss_rejection():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));decision=RiskManager().calculate(signal,10000,RiskConfig(),daily_pnl=-500)
    assert not decision.approved
def test_only_one_trade_can_be_active():
    signal=ConflictResolver().signal(scenario("a","LONG",.7))
    assert not RiskManager().calculate(signal,10000,RiskConfig(),open_positions=1).approved
    assert not RiskManager().calculate(signal,10000,RiskConfig(),active_orders=1).approved
def test_first_loss_halves_trade_capital():
    signal=ConflictResolver().signal(scenario("a","LONG",.7))
    decision=RiskManager().calculate(signal,10000,RiskConfig(),consecutive_losses=1,last_loss_at=1,now=2)
    assert decision.approved and decision.capital_multiplier==.5
    assert decision.risk_amount==50 and decision.position_size==10
def test_two_losses_pause_for_twelve_hours_then_keep_half_size():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));cfg=RiskConfig();last=1_000
    paused=RiskManager().calculate(signal,10000,cfg,consecutive_losses=2,last_loss_at=last,now=last+11*3_600_000)
    resumed=RiskManager().calculate(signal,10000,cfg,consecutive_losses=2,last_loss_at=last,now=last+12*3_600_000)
    assert not paused.approved and paused.cooldown_until==last+12*3_600_000
    assert resumed.approved and resumed.risk_amount==50
def test_three_losses_pause_for_one_day():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));cfg=RiskConfig();last=1_000
    decision=RiskManager().calculate(signal,10000,cfg,consecutive_losses=3,last_loss_at=last,now=last+23*3_600_000)
    assert not decision.approved and decision.cooldown_until==last+24*3_600_000
def test_demo_simulation_ignores_pnl_limits_and_uses_full_size():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));cfg=RiskConfig();last=1_000
    decision=RiskManager().calculate(signal,10000,cfg,daily_pnl=-1000,consecutive_losses=3,
      last_loss_at=last,now=last+1_000,ignore_loss_limits=True)
    assert decision.approved and decision.capital_multiplier==1
    assert decision.risk_amount==100 and decision.cooldown_until is None
def test_demo_simulation_still_rejects_an_active_trade():
    signal=ConflictResolver().signal(scenario("a","LONG",.7))
    decision=RiskManager().calculate(signal,10000,RiskConfig(),open_positions=1,ignore_loss_limits=True)
    assert not decision.approved and decision.rejection_reason=="Another trade is still active"
def test_elliott_confidence_is_preserved_without_model_scoring():
    import asyncio
    from unittest.mock import AsyncMock
    from src.service import DecisionService

    async def check():
        service = DecisionService("unused", "unused")
        service.pub = AsyncMock()
        service.resolve_after_delay = AsyncMock()
        item = scenario("elliott", "LONG", 1).model_copy(update={"setup_type": "ELLIOTT_WAVE3"})
        result = await service.evaluate(item)
        assert result == {"scenario_id": "elliott", "confidence": 1}
        assert item.confidence == 1
        await asyncio.gather(*service.pending.values())
        assert await service.evaluate(scenario("other", "LONG", 1)) is None
    asyncio.run(check())


def test_waiting_signals_retry_sequentially_after_position_closes():
    import asyncio
    from unittest.mock import AsyncMock
    from src.service import DecisionService

    async def check():
        service=DecisionService("unused","unused")
        first=ConflictResolver().signal(scenario("first","LONG",1))
        second=ConflictResolver().signal(scenario("second","LONG",1))
        first=first.model_copy(update={"created_at":1});second=second.model_copy(update={"created_at":2})
        service.signals={first.signal_id:first,second.signal_id:second}
        service.waiting={first.signal_id,second.signal_id}
        service.assess=AsyncMock(return_value=RiskDecision(signal_id=first.signal_id,approved=True))
        await service.retry_waiting()
        service.assess.assert_awaited_once_with(first)
    asyncio.run(check())
