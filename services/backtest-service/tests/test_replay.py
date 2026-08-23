import pytest
from pydantic import ValidationError

from src.models import BacktestCreate
from src.replay import FrozenModel, TemplateModel


def test_train_and_test_periods_cannot_overlap():
    with pytest.raises(ValidationError):
        BacktestCreate(
            symbol="BTC-USDT-SWAP",
            train_from=100,
            train_to=300,
            test_from=200,
            test_to=400,
        )


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
