import pytest
from pydantic import ValidationError
from types import SimpleNamespace

from src.models import BacktestConfig, BacktestCreate
from src.replay import (_chart_candles, _execution_plan, _target_allocations,
                        _template_stop_distance_allowed, initialize_indicators)


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
    assert targets==pytest.approx([100.71])


def test_configured_target_allocations_require_matching_target_count():
    assert _target_allocations(SimpleNamespace(target_allocations=[.4,.6]),2)==[.4,.6]
    assert _target_allocations(SimpleNamespace(target_allocations=[.4,.6]),1)==[1]


def test_optional_stop_band_is_checked_on_actual_fill():
    config=SimpleNamespace(minimum_stop_percent=.75,maximum_stop_percent=1.5)
    assert _template_stop_distance_allowed(100,101,config)
    assert not _template_stop_distance_allowed(100,100.5,config)


def test_chart_window_keeps_real_candles_instead_of_aggregating_them():
    candles = [
        {"timestamp": index * 60_000, "open": index, "high": index + 1,
         "low": index - 1, "close": index + .5, "volume": 1}
        for index in range(5)
    ]

    result = _chart_candles(candles, maximum=3)

    assert [item["timestamp"] for item in result] == [120_000, 180_000, 240_000]
    assert [item["open"] for item in result] == [2, 3, 4]


def test_algorithm_overrides_validate_target_allocations():
    with pytest.raises(ValidationError):
        BacktestConfig(algorithm_overrides={"DEMO_SMC_V1": {
            "risk_reward": [2, 3], "target_allocations": [1],
        }})

    config = BacktestConfig(algorithm_overrides={"DEMO_SMC_V1": {
        "minimum_adx": 25, "risk_reward": [2], "target_allocations": [1],
    }})
    assert config.algorithm_overrides["DEMO_SMC_V1"].minimum_adx == 25
    assert config.algorithm_overrides["DEMO_SMC_V1"].require_liquidity_sweep_before_ob
    assert config.algorithm_overrides["DEMO_SMC_V1"].require_ob_in_ote_zone
    assert config.algorithm_overrides["DEMO_SMC_V1"].require_ob_caused_bos


def test_optimizer_bounds_are_ordered():
    with pytest.raises(ValidationError):
        BacktestConfig(optimization={
            "enabled": True, "parameter_bounds": {"minimum_adx": [30, 10]},
        })

    config = BacktestConfig(optimization={"enabled": True})
    assert config.optimization.parameter_grid == {}


def test_atr_and_adx_are_initialized_on_candles():
    values = [{
        "symbol": "BTC-USDT-SWAP", "timeframe": "M1", "timestamp": index * 60_000,
        "open": 100 + index, "high": 101 + index, "low": 99 + index,
        "close": 100.5 + index, "volume": 10,
    } for index in range(40)]

    initialize_indicators({"M1": values}, {14, 20})

    assert "atr:14" in values[-1]["indicators"]
    assert "adx:14" in values[-1]["indicators"]
    assert "adx:20" in values[-1]["indicators"]
