from src.models import RiskConfig, TradeSignal
from src.risk import RiskManager


def signal():
    return TradeSignal(source_signal_id="source",symbol="BTC-USDT",direction="LONG",entry_price=100,
                       stop_loss_price=95,take_profit_prices=[110],quality_score=.5,config_id="DEMO")


def test_risk_position_size_is_fixed_by_config_not_ml_score():
    first=RiskManager().calculate(signal(),10000,RiskConfig())
    other=signal().model_copy(update={"quality_score":.99})
    second=RiskManager().calculate(other,10000,RiskConfig())
    assert first.approved and first.risk_amount==100 and first.position_size==20
    assert second.risk_amount==first.risk_amount


def test_daily_loss_rejection():
    assert not RiskManager().calculate(signal(),10000,RiskConfig(),daily_pnl=-500).approved


def test_only_one_trade_can_be_active():
    assert not RiskManager().calculate(signal(),10000,RiskConfig(),open_positions=1).approved
    assert not RiskManager().calculate(signal(),10000,RiskConfig(),active_orders=1).approved


def test_loss_streak_controls_are_deterministic():
    cfg=RiskConfig();last=1_000
    first=RiskManager().calculate(signal(),10000,cfg,consecutive_losses=1,last_loss_at=1,now=2)
    paused=RiskManager().calculate(signal(),10000,cfg,consecutive_losses=2,last_loss_at=last,now=last+11*3_600_000)
    resumed=RiskManager().calculate(signal(),10000,cfg,consecutive_losses=2,last_loss_at=last,now=last+12*3_600_000)
    assert first.approved and first.risk_amount==50
    assert not paused.approved and resumed.approved and resumed.risk_amount==50
