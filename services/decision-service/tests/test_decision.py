from src.models import *
from src.probability import ProbabilityEngine
from src.resolver import ConflictResolver
from src.risk import RiskManager
from src.adaptive import AdaptiveModel,bandit_adjust

def scenario(id,direction,confidence):return Scenario(id=id,symbol="BTC-USDT",timeframe="M15",direction=direction,setup_type="TEST",confidence=confidence,entry_zone_low=99,entry_zone_high=101,stop_loss_price=95,take_profit_prices=[110],expires_at=9999999999999)
def test_probability_is_bounded():
    result=ProbabilityEngine().calculate([100,-100,1]);assert 0<=result.confidence<=1
def test_conflict_rejects_inconclusive_directions():
    selected,rejected=ConflictResolver().select([scenario("a","LONG",.7),scenario("b","SHORT",.65)])
    assert selected is None and len(rejected)==2
def test_conflict_selects_clear_winner():
    selected,_=ConflictResolver().select([scenario("a","LONG",.8),scenario("b","SHORT",.65)])
    assert selected.id=="a"
def test_risk_position_size():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));decision=RiskManager().calculate(signal,10000,RiskConfig())
    assert decision.approved and decision.risk_amount==100 and decision.position_size==20
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
def test_adaptive_model_blends_safely():
    m=AdaptiveModel(.25);m.load({"version":"v1","feature_names":["confidence"],"weights":[2],"bias":0});assert .6<m.blend(.6,{"confidence":1})<.9
def test_bandit_adjustment_is_bounded():assert round(bandit_adjust(.6,1),2)==.65 and round(bandit_adjust(.6,0),2)==.55
