import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from src.models import BacktestConfig, BacktestCreate
from src.replay import _execution_plan, _target_allocations, _template_stop_distance_allowed


def test_train_and_test_periods_cannot_overlap():
    with pytest.raises(ValidationError):
        BacktestCreate(symbol="BTC-USDT-SWAP",train_from=100,train_to=300,test_from=200,test_to=400)


def test_smc_execution_timeframe_is_selected_automatically():
    request=BacktestCreate(symbol="BTC-USDT-SWAP",timeframe="H4",timeframes=["H4","M15","H1"])
    assert request.timeframe=="M15"


def test_execution_plan_is_structural_and_deterministic():
    setup=SimpleNamespace(direction="LONG",entry_zone_low=99.9,entry_zone_high=100.1,
                          stop_loss_price=99.95,take_profit_prices=[100.1,100.15])
    stop,targets=_execution_plan(100.1,setup,.3,.01)
    assert stop==pytest.approx(99.79)
    assert targets==pytest.approx([100.71,101.01])


def test_configured_target_allocations_require_matching_target_count():
    assert _target_allocations(SimpleNamespace(target_allocations=[.4,.6]),2)==[.4,.6]
    assert _target_allocations(SimpleNamespace(target_allocations=[.4,.6]),1)==[1]


def test_optional_stop_band_is_checked_on_actual_fill():
    config=SimpleNamespace(minimum_stop_percent=.75,maximum_stop_percent=1.5)
    assert _template_stop_distance_allowed(100,101,config)
    assert not _template_stop_distance_allowed(100,100.5,config)
