from src.models import *
from src.probability import ProbabilityEngine
from src.resolver import ConflictResolver
from src.risk import RiskManager

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
def test_daily_loss_rejection():
    signal=ConflictResolver().signal(scenario("a","LONG",.7));decision=RiskManager().calculate(signal,10000,RiskConfig(),daily_pnl=-500)
    assert not decision.approved
