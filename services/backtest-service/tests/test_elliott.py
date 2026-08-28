import pytest

from src.elliott import (
    Pivot, _elliott_position_quantity, _fee_adjusted_break_even_stop, _fixed_rr_target,
    atr_zigzag, detect_patterns, run_elliott_replay,
)
from src.models import BacktestConfig, ElliottConfig, StrategyType


def candles(prices, step=3_600_000, scale=1):
    result = []
    for index, price in enumerate(prices):
        previous = prices[max(0, index - 1)]
        result.append({"timestamp": index * step, "open": previous, "high": price + scale * .2,
                       "low": price - scale * .2, "close": price, "volume": 100 + index})
    return result


def loose_config():
    return ElliottConfig(
        macro_filter="OFF", atr_period=2, zigzag_reversal_atr=.5, min_swing_atr=0,
        min_swing_candles=1, max_swing_candles=None, wave1_min_atr=0,
        wave1_min_candles=1, wave1_max_candles=None, wave1_min_efficiency=0,
        require_bos=False, wave2_min_retracement=.1, wave2_max_retracement=.95,
        wave2_min_time_ratio=0, wave2_max_time_ratio=20, choch_min_atr=0,
        choch_min_body_ratio=0, minimum_rr=.1,
    )


def test_config_enforces_timeframe_hierarchy_and_tp_allocations():
    with pytest.raises(ValueError):
        ElliottConfig(macro_timeframe="M15", structure_timeframe="H1", entry_timeframe="H4")
    with pytest.raises(ValueError):
        ElliottConfig(take_profit_extensions=[1, 1.618], take_profit_allocations=[1])
    with pytest.raises(ValueError):
        ElliottConfig(take_profit_count=2, take_profit_rr=2, second_take_profit_rr=1)
    assert ElliottConfig(take_profit_count=1, take_profit_rr=2, second_take_profit_rr=1).take_profit_count == 1


def test_fixed_rr_target_uses_actual_stop_distance():
    assert _fixed_rr_target(100, 98, "LONG", 2) == pytest.approx(104)
    assert _fixed_rr_target(100, 103, "SHORT", 1.5) == pytest.approx(95.5)


def test_margin_uses_the_whole_asset_capital_and_reinvestment_is_optional():
    assert _elliott_position_quantity(100, 100, 10, True, 5, True) == pytest.approx(50)
    assert _elliott_position_quantity(150, 100, 10, True, 5, False) == pytest.approx(50)
    assert _elliott_position_quantity(80, 100, 10, True, 5, False) == pytest.approx(40)
    assert _elliott_position_quantity(100, 100, 10, False, 5, True) == pytest.approx(10)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_break_even_stop_covers_fees_and_slippage(direction):
    entry, maker, taker, slip = 100.0, .0002, .0005, .0002
    stop = _fee_adjusted_break_even_stop(entry, direction, maker, taker, slip, .01)
    side = 1 if direction == "LONG" else -1
    exit_price = stop * (1 - slip * side)
    net = (exit_price - entry) * side - entry * maker - exit_price * taker

    assert net >= -1e-12
    assert net < .02


def test_atr_zigzag_confirmation_never_precedes_pivot():
    pivots = atr_zigzag(candles([100, 98, 95, 99, 105, 101, 97, 103, 110]), loose_config())
    assert len(pivots) >= 3
    assert all(item.confirmed_at >= item.timestamp for item in pivots)
    assert all(left.kind != right.kind for left, right in zip(pivots, pivots[1:]))


def test_wave2_invalidation_rule(monkeypatch):
    structure = candles([100] * 12)
    pivots = [
        Pivot(1, 1_000, 2_000, 100, "LOW", 2),
        Pivot(4, 4_000, 5_000, 110, "HIGH", 2),
        Pivot(7, 7_000, 8_000, 99, "LOW", 2),
    ]
    monkeypatch.setattr("src.elliott.atr_zigzag", lambda items, config: pivots if items is structure else [])
    patterns, _, _ = detect_patterns(structure, candles([100] * 12, 900_000), candles([100] * 4, 14_400_000), loose_config())
    assert patterns[0].state == "INVALID"
    assert patterns[0].invalid_reason == "WAVE2_BEYOND_P0"


def test_complete_impulse_and_abc_are_classified(monkeypatch):
    structure = candles([100] * 20)
    sequence = [
        Pivot(1, 1_000, 2_000, 100, "LOW", 2), Pivot(3, 3_000, 4_000, 110, "HIGH", 2),
        Pivot(5, 5_000, 6_000, 105, "LOW", 2), Pivot(7, 7_000, 8_000, 122, "HIGH", 2),
        Pivot(9, 9_000, 10_000, 113, "LOW", 2), Pivot(11, 11_000, 12_000, 126, "HIGH", 2),
        Pivot(13, 13_000, 14_000, 116, "LOW", 2), Pivot(15, 15_000, 16_000, 121, "HIGH", 2),
        Pivot(17, 17_000, 18_000, 111, "LOW", 2),
    ]
    monkeypatch.setattr("src.elliott.atr_zigzag", lambda items, config: sequence if items is structure else [])
    patterns, _, _ = detect_patterns(structure, candles([100] * 20, 900_000), candles([100] * 5, 14_400_000), loose_config())
    complete = next(item for item in patterns if item.points["P0"].timestamp == 1_000)
    assert complete.state == "ABC_COMPLETE"
    assert list(complete.points) == ["P0", "P1", "P2", "P3", "P4", "P5", "A", "B", "C"]
    assert complete.features["correction_type"] == "ZIGZAG_ABC"


def test_replay_returns_serializable_wave_contract():
    config = BacktestConfig(strategy=StrategyType.ELLIOTT, elliott=loose_config())
    data = {
        "H4": candles([100, 101, 102, 103], 14_400_000),
        "H1": candles([100, 98, 95, 99, 105, 101, 98, 103, 110, 106, 114]),
        "M15": candles([100, 99, 98, 97, 99, 101, 103, 100, 98, 99, 102, 105, 108, 111], 900_000),
    }
    result = run_elliott_replay(data, config)
    assert result["elliott_diagnostics"]["lookahead_safe"] is True
    assert "elliott_patterns" in result
    assert set(result["chart_candles_by_timeframe"]) == {"H4", "H1", "M15"}
    assert result["final_capital"] == pytest.approx(config.initial_capital + result["net_profit"])
    for trade in result["trades"]:
        assert len(trade["take_profit_prices"]) == 2
        assert trade["exits"]
        assert sum(exit_fill["pnl"] for exit_fill in trade["exits"]) == pytest.approx(trade["pnl"])
        if trade["direction"] == "LONG":
            assert trade["initial_stop"] < trade["entry_price"]
        else:
            assert trade["initial_stop"] > trade["entry_price"]
