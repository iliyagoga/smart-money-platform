import pytest
from pydantic import ValidationError

from src.models import BacktestConfig, BacktestCreate
from types import SimpleNamespace

from smc_core.models import Timeframe
from src.replay import (
    FrozenModel, TemplateModel, _execution_plan, _scenario_outcome,
    _template_stop_distance_allowed, run_smc_replay,
)


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
    assert model.probability("REVERSAL", .6) == pytest.approx(.5825)


def test_local_outcomes_calibrate_instead_of_replacing_structural_confidence():
    model = TemplateModel(outcomes={"REVERSAL": [0] * 20})

    assert model.probability("REVERSAL", .7) > .45


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


def test_template_stop_distance_band_is_checked_on_actual_fill():
    template = SimpleNamespace(minimum_stop_percent=.75, maximum_stop_percent=1.5)

    assert _template_stop_distance_allowed(100, 101, template) is True
    assert _template_stop_distance_allowed(100, 100.5, template) is False
    assert _template_stop_distance_allowed(100, 102, template) is False


def test_scenario_outcome_cannot_use_the_signal_candle():
    scenario = SimpleNamespace(
        direction="LONG", created_at=0, expires_at=600_000,
        entry_zone_low=99, entry_zone_high=101, stop_loss_price=98, take_profit_prices=[102],
    )
    candles = [
        SimpleNamespace(timestamp=0, timeframe=Timeframe.M1, open=100, high=103, low=99),
        SimpleNamespace(timestamp=60_000, timeframe=Timeframe.M1, open=100, high=103, low=99),
    ]

    assert _scenario_outcome(scenario, candles, ready_at=60_000) == 1


def test_unfilled_or_unresolved_scenario_is_not_learned_as_a_loss():
    scenario = SimpleNamespace(
        direction="LONG", created_at=0, expires_at=180_000,
        entry_zone_low=99, entry_zone_high=101, stop_loss_price=98, take_profit_prices=[102],
    )
    no_touch = [SimpleNamespace(timestamp=60_000, timeframe=Timeframe.M1, open=110, high=111, low=109)]
    unresolved = [SimpleNamespace(timestamp=60_000, timeframe=Timeframe.M1, open=100, high=101, low=99)]

    assert _scenario_outcome(scenario, no_touch, ready_at=60_000) is None
    assert _scenario_outcome(scenario, unresolved, ready_at=60_000) is None


def test_replay_waits_for_next_closed_candle_and_trade_pnl_includes_entry_fee(monkeypatch):
    scenario = SimpleNamespace(
        id="scenario", direction="LONG", setup_type="TEST", confidence=.9, priority=1,
        timeframe=Timeframe.M1, created_at=0, expires_at=600_000,
        entry_zone_low=99.9, entry_zone_high=100.1, stop_loss_price=99.5,
        take_profit_prices=[101], reasons=[],
    )

    class Pipeline:
        def process(self, candle): pass

    class Store:
        def get(self, template_id): return SimpleNamespace(risk_reward=[2])

    class Manager:
        def __init__(self, store): self.store=Store();self.calls=0;self.diagnostics={}
        def generate_top_down(self, *args):
            self.calls += 1
            return [scenario] if self.calls == 1 else []

    monkeypatch.setattr("src.replay.AnalysisPipeline", Pipeline)
    monkeypatch.setattr("src.replay.ScenarioManager", Manager)
    values = [
        {"symbol":"BTC-USDT-SWAP","timeframe":"M1","timestamp":0,"open":100,"high":103,"low":99,"close":100,"volume":1000},
        {"symbol":"BTC-USDT-SWAP","timeframe":"M1","timestamp":60_000,"open":100,"high":100.1,"low":99.9,"close":100,"volume":1000},
        {"symbol":"BTC-USDT-SWAP","timeframe":"M1","timestamp":120_000,"open":100,"high":102,"low":100,"close":101,"volume":1000},
    ]
    config = BacktestConfig(initial_capital=1000, fee_percent=.1, maker_fee_percent=.1,
                            taker_fee_percent=.1, slippage_percent=0, confidence_threshold=.5)

    result = run_smc_replay({"M1": values}, "M1", config, "/tmp")

    assert result["trades"][0]["entry_time"] == 120_000
    assert result["trades"][0]["entry_time"] > result["scenarios"][0]["timestamp"]
    assert sum(item["pnl"] for item in result["trades"]) == pytest.approx(result["net_profit"])
    assert result["scenarios"][0]["decision"] == "EXECUTED"
