import pytest
from pydantic import ValidationError

from src.models import BacktestCreate
from types import SimpleNamespace

from src.replay import FrozenModel, TemplateModel, _execution_plan


def test_train_and_test_periods_cannot_overlap():
    with pytest.raises(ValidationError):
        BacktestCreate(
            symbol="BTC-USDT-SWAP",
            train_from=100,
            train_to=300,
            test_from=200,
            test_to=400,
        )


def test_smc_execution_timeframe_is_selected_automatically():
    request = BacktestCreate(symbol="BTC-USDT-SWAP", timeframe="H4", timeframes=["H4", "M15", "H1"])
    assert request.timeframe == "M15"


def test_local_model_is_deterministic_and_smoothed():
    model = TemplateModel()
    model.learn("REVERSAL", 1)
    model.learn("REVERSAL", 0)
    assert model.probability("REVERSAL", .6) == pytest.approx(.55)


def test_frozen_model_blends_prediction_with_scenario_score():
    model = FrozenModel("v1", ["confidence"], [1], 0)
    first = model.probability("REVERSAL", .6)
    second = model.probability("REVERSAL", .6)
    assert first == second
    assert 0 < first < 1


def test_execution_plan_enforces_minimum_long_stop_and_rebases_targets():
    scenario = SimpleNamespace(
        direction="LONG", entry_zone_low=99.9, entry_zone_high=100.1,
        stop_loss_price=99.95, take_profit_prices=[100.1, 100.15],
    )

    stop, targets = _execution_plan(100.1, scenario, .3, .01)

    assert stop == pytest.approx(99.79)
    assert targets == pytest.approx([100.71, 101.01])
    assert stop < 100.1 < targets[0]


def test_execution_plan_corrects_short_stop_on_wrong_side_of_fill():
    scenario = SimpleNamespace(
        direction="SHORT", entry_zone_low=99.9, entry_zone_high=100.1,
        stop_loss_price=100.05, take_profit_prices=[99.9, 99.85],
    )

    stop, targets = _execution_plan(100.1, scenario, .3, .01)

    assert stop == pytest.approx(100.41)
    assert targets == pytest.approx([99.49, 99.19])
    assert targets[0] < 100.1 < stop
