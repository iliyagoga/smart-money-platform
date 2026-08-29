import pytest

from src.elliott import (
    Pattern, Pivot, _elliott_position_quantity, _fee_adjusted_break_even_stop,
    _fixed_rr_target, _liquidation_price, _macro_direction, _round_trade_prices,
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
        choch_min_body_ratio=0, require_strict_choch=False, minimum_rr=.1,
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
    # A 1% risk budget with a one-unit stop permits one unit. Margin is a cap,
    # never the primary sizing rule.
    assert _elliott_position_quantity(100, 100, 10, 9, 1, 100, True, 5, True, .01) == pytest.approx(1)
    assert _elliott_position_quantity(150, 100, 10, 9, 1, 100, True, 5, False, .01) == pytest.approx(1)
    assert _elliott_position_quantity(80, 100, 10, 9, 1, 100, True, 5, False, .01) == pytest.approx(.8)
    assert _elliott_position_quantity(100, 100, 10, 9, 100, 25, False, 5, True, .01) == pytest.approx(2.5)


def test_prices_and_quantity_follow_exchange_steps():
    entry, stop, targets = _round_trade_prices(100.04, 98.06, [103.01, 104.09], "LONG", .1)
    assert entry == pytest.approx(100)
    assert stop == pytest.approx(98)
    assert targets == pytest.approx([103.1, 104.1])
    assert _elliott_position_quantity(100, 100, 3, 2, 100, 100, False, 1, True, .1) == pytest.approx(33.3)


def test_position_risk_is_capped_by_configured_percent():
    quantity = _elliott_position_quantity(10_000, 10_000, 100, 95, 1, 100, True, 3, True, .01)
    assert quantity == pytest.approx(20)
    assert quantity * (100 - 95) == pytest.approx(100)


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_break_even_stop_covers_fees_and_slippage(direction):
    entry, maker, taker, slip = 100.0, .0002, .0005, .0002
    stop = _fee_adjusted_break_even_stop(entry, direction, maker, taker, slip, .01)
    side = 1 if direction == "LONG" else -1
    exit_price = stop * (1 - slip * side)
    net = (exit_price - entry) * side - entry * maker - exit_price * taker

    assert net >= -1e-12
    assert net < .02


def test_retrace_waits_for_a_real_touch_and_expires(monkeypatch):
    pattern = Pattern(
        "signal", "LONG",
        {"P0": Pivot(0, 0, 0, 90, "LOW", 1), "P1": Pivot(1, 0, 0, 110, "HIGH", 1),
         "P2": Pivot(2, 0, 0, 100, "LOW", 1)},
        "WAVE3_POTENTIAL", {"choch_level": 100, "choch_close": 110}, signal_time=1,
    )
    monkeypatch.setattr("src.elliott.detect_patterns", lambda *args: ([pattern], [], []))
    entry = [
        {"timestamp": 0, "open": 108, "high": 110, "low": 107, "close": 109, "volume": 10},
        {"timestamp": 900_000, "open": 107, "high": 108, "low": 106, "close": 107, "volume": 10},
        {"timestamp": 1_800_000, "open": 106, "high": 106, "low": 104, "close": 105, "volume": 10},
        {"timestamp": 2_700_000, "open": 105, "high": 116, "low": 104, "close": 115, "volume": 10},
    ]
    data = {"H4": entry, "H1": entry, "M15": entry}
    config = BacktestConfig(
        strategy="ELLIOTT", tick_size=.1, lot_size=.01, minimum_order_size=.01,
        maker_fee_percent=.02, taker_fee_percent=.05, slippage_percent=0,
        elliott=loose_config().model_copy(update={
            "entry_expiry_bars": 4, "take_profit_count": 1, "take_profit_rr": 2,
        }),
    )

    result = run_elliott_replay(data, config)

    assert result["trades"][0]["entry_time"] == 1_800_000
    assert result["trades"][0]["entry_price"] == 105
    trade = result["trades"][0]
    expected_maker_fees = (trade["entry_price"] + trade["exit_price"]) * trade["quantity"] * .0002
    assert trade["fees"] == pytest.approx(expected_maker_fees)
    expired = run_elliott_replay(
        data, config.model_copy(update={"elliott": config.elliott.model_copy(update={"entry_expiry_bars": 1})}),
    )
    assert expired["trades"] == []
    assert expired["elliott_diagnostics"]["expired_signals"] == 1


def test_margin_position_is_liquidated_before_a_distant_structural_stop(monkeypatch):
    pattern = Pattern(
        "signal", "LONG",
        {"P0": Pivot(0, 0, 0, 50, "LOW", 1), "P1": Pivot(1, 0, 0, 120, "HIGH", 1),
         "P2": Pivot(2, 0, 0, 50, "LOW", 1)},
        "WAVE3_POTENTIAL", {"choch_level": 90, "choch_close": 100}, signal_time=1,
    )
    monkeypatch.setattr("src.elliott.detect_patterns", lambda *args: ([pattern], [], []))
    entry = [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
        {"timestamp": 900_000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 10},
        {"timestamp": 1_800_000, "open": 100, "high": 100, "low": 75, "close": 80, "volume": 10},
    ]
    config = BacktestConfig(
        strategy="ELLIOTT", leverage=5, tick_size=.1, lot_size=.01, minimum_order_size=.01,
        fee_percent=0, slippage_percent=0,
        elliott=loose_config().model_copy(update={"entry_model": "CHOCH_MARKET", "use_margin": True}),
    )

    result = run_elliott_replay({"H4": entry, "H1": entry, "M15": entry}, config)

    assert result["trades"][0]["reason"] == "LIQUIDATION"


def test_liquidation_price_includes_maintenance_margin_fees_and_funding():
    position = {
        "direction": "LONG", "entry_price": 100, "quantity": 10,
        "entry_fee_rate": .001, "funding": 2,
    }
    config = BacktestConfig(
        leverage=10, maintenance_margin_percent=.5, liquidation_fee_percent=.5,
    )

    price = _liquidation_price(position, config, taker_fee=.001)

    # At this price the remaining equity equals the configured maintenance margin.
    exit_cost = price * 10 * (.001 + .005)
    equity = 100 + (price - 100) * 10 - 1 - 2 - exit_cost
    assert equity == pytest.approx(5)


def test_liquidation_after_partial_exit_uses_remaining_quantity():
    position = {
        "direction": "LONG", "entry_price": 100, "quantity": 10, "remaining": 5,
        "entry_fee_rate": 0, "funding": 5,
    }
    config = BacktestConfig(
        leverage=10, maintenance_margin_percent=0, liquidation_fee_percent=0,
    )

    assert _liquidation_price(position, config, taker_fee=0) == pytest.approx(91)


def test_elliott_replay_rejects_empty_entry_dataset():
    config = BacktestConfig(strategy="ELLIOTT", elliott=loose_config())

    with pytest.raises(ValueError, match="no Elliott entry candles"):
        run_elliott_replay({"H4": [], "H1": [], "M15": []}, config)


def test_minimum_rr_is_checked_against_executable_fixed_target(monkeypatch):
    with pytest.raises(ValueError, match="first take-profit RR must satisfy minimum RR"):
        ElliottConfig(take_profit_count=1, take_profit_rr=1, minimum_rr=2)


def test_wave1_break_retrace_waits_for_break_then_later_retest(monkeypatch):
    pattern = Pattern(
        "wave1", "LONG",
        {"P0": Pivot(0, 0, 0, 90, "LOW", 1), "P1": Pivot(1, 0, 0, 105, "HIGH", 1),
         "P2": Pivot(2, 0, 0, 98, "LOW", 1)},
        "WAVE3_POTENTIAL", {"choch_level": 101, "choch_close": 102}, signal_time=1,
    )
    monkeypatch.setattr("src.elliott.detect_patterns", lambda *args: ([pattern], [], []))
    entry = [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
        {"timestamp": 900_000, "open": 102, "high": 106, "low": 101, "close": 106, "volume": 100},
        {"timestamp": 1_800_000, "open": 106, "high": 106, "low": 105, "close": 105.5, "volume": 100},
        {"timestamp": 2_700_000, "open": 105.5, "high": 106, "low": 105, "close": 105.5, "volume": 100},
    ]
    elliott = loose_config().model_copy(update={
        "entry_model": "WAVE1_BREAK_RETRACE", "take_profit_count": 1,
    })
    config = BacktestConfig(
        strategy="ELLIOTT", fee_percent=0, slippage_percent=0,
        tick_size=.1, lot_size=.01, minimum_order_size=.01, elliott=elliott,
    )

    result = run_elliott_replay({"H4": entry, "H1": entry, "M15": entry}, config)

    assert result["trades"][0]["pattern_id"] == "wave1"
    assert result["trades"][0]["entry_time"] == 1_800_000
    assert result["trades"][0]["entry_price"] == pytest.approx(105)


def test_break_even_at_one_r_closes_on_later_retrace(monkeypatch):
    pattern = Pattern(
        "one-r", "LONG",
        {"P0": Pivot(0, 0, 0, 90, "LOW", 1), "P1": Pivot(1, 0, 0, 110, "HIGH", 1),
         "P2": Pivot(2, 0, 0, 98, "LOW", 1)},
        "WAVE3_POTENTIAL", {"choch_level": 99, "choch_close": 100}, signal_time=1,
    )
    monkeypatch.setattr("src.elliott.detect_patterns", lambda *args: ([pattern], [], []))
    entry = [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
        {"timestamp": 900_000, "open": 100, "high": 102.5, "low": 99, "close": 102, "volume": 100},
        {"timestamp": 1_800_000, "open": 102, "high": 102, "low": 99.9, "close": 100, "volume": 100},
    ]
    elliott = loose_config().model_copy(update={
        "entry_model": "CHOCH_MARKET", "take_profit_count": 1,
        "take_profit_rr": 3, "break_even_at_one_r": True,
    })
    config = BacktestConfig(
        strategy="ELLIOTT", fee_percent=0, slippage_percent=0,
        tick_size=.1, lot_size=.01, minimum_order_size=.01, elliott=elliott,
    )

    result = run_elliott_replay({"H4": entry, "H1": entry, "M15": entry}, config)

    assert result["trades"][0]["reason"] == "BREAK_EVEN"
    assert result["trades"][0]["exit_price"] == pytest.approx(100)


def test_invalid_first_signal_does_not_block_next_valid_signal(monkeypatch):
    def pattern(identifier, p2):
        return Pattern(
            identifier, "LONG",
            {"P0": Pivot(0, 0, 0, 90, "LOW", 1), "P1": Pivot(1, 0, 0, 110, "HIGH", 1),
             "P2": Pivot(2, 0, 0, p2, "LOW", 1)},
            "WAVE3_POTENTIAL", {"choch_level": 99, "choch_close": 100}, signal_time=1,
        )
    monkeypatch.setattr(
        "src.elliott.detect_patterns", lambda *args: ([pattern("invalid", 101), pattern("valid", 98)], [], []),
    )
    entry = [
        {"timestamp": 0, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
        {"timestamp": 900_000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
        {"timestamp": 1_800_000, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 100},
    ]
    elliott = loose_config().model_copy(update={"entry_model": "CHOCH_MARKET", "take_profit_count": 1})
    config = BacktestConfig(
        strategy="ELLIOTT", fee_percent=0, slippage_percent=0,
        tick_size=.1, lot_size=.01, minimum_order_size=.01, elliott=elliott,
    )

    result = run_elliott_replay({"H4": entry, "H1": entry, "M15": entry}, config)

    assert result["trades"][0]["pattern_id"] == "valid"


def test_atr_zigzag_confirmation_never_precedes_pivot():
    pivots = atr_zigzag(candles([100, 98, 95, 99, 105, 101, 97, 103, 110]), loose_config())
    assert len(pivots) >= 3
    assert all(item.confirmed_at >= item.timestamp + 3_600_000 for item in pivots)
    assert all(left.kind != right.kind for left, right in zip(pivots, pivots[1:]))


def test_macro_filter_never_reads_an_unclosed_higher_timeframe_candle():
    macro = candles([100, 99, 120], 14_400_000)

    assert _macro_direction(macro, 36_000_000, "STRUCTURE", "H4") == "BOTH"
    assert _macro_direction(macro, 43_200_000, "STRUCTURE", "H4") == "LONG"


def test_wave2_invalidation_rule(monkeypatch):
    structure = candles([100] * 12)
    pivots = [
        Pivot(1, 1_000, 2_000, 100, "LOW", 2),
        Pivot(4, 4_000, 5_000, 110, "HIGH", 2),
        Pivot(7, 7_000, 8_000, 99, "LOW", 2),
    ]
    monkeypatch.setattr("src.elliott.atr_zigzag", lambda items, config, timeframe=None: pivots if items is structure else [])
    patterns, _, _ = detect_patterns(structure, candles([100] * 12, 900_000), candles([100] * 4, 14_400_000), loose_config())
    assert patterns[0].state == "INVALID"
    assert patterns[0].invalid_reason == "WAVE2_BEYOND_P0"


def test_choch_after_confirmed_wave3_pivot_cannot_revive_old_pattern(monkeypatch):
    structure = candles([100] * 8, 1_000)
    entry = candles([100, 100, 100, 100, 100, 100, 112, 112], 1_000)
    structure_pivots = [
        Pivot(0, 0, 1_000, 100, "LOW", 2),
        Pivot(1, 1_000, 2_000, 110, "HIGH", 2),
        Pivot(2, 2_000, 3_000, 105, "LOW", 2),
        Pivot(4, 4_000, 5_000, 115, "HIGH", 2),
    ]
    entry_pivots = [Pivot(3, 3_000, 3_500, 108, "HIGH", 1)]
    monkeypatch.setattr(
        "src.elliott.atr_zigzag",
        lambda items, config, timeframe=None: structure_pivots if items is structure else entry_pivots if items is entry else [],
    )

    patterns, _, _ = detect_patterns(structure, entry, candles([100] * 3, 4_000), loose_config())
    pattern = next(item for item in patterns if item.points["P0"].timestamp == 0)

    assert pattern.features["signal_deadline"] == 5_000
    assert pattern.signal_time is None


def test_complete_impulse_and_abc_are_classified(monkeypatch):
    structure = candles([100] * 20)
    sequence = [
        Pivot(1, 1_000, 2_000, 100, "LOW", 2), Pivot(3, 3_000, 4_000, 110, "HIGH", 2),
        Pivot(5, 5_000, 6_000, 105, "LOW", 2), Pivot(7, 7_000, 8_000, 122, "HIGH", 2),
        Pivot(9, 9_000, 10_000, 113, "LOW", 2), Pivot(11, 11_000, 12_000, 126, "HIGH", 2),
        Pivot(13, 13_000, 14_000, 116, "LOW", 2), Pivot(15, 15_000, 16_000, 121, "HIGH", 2),
        Pivot(17, 17_000, 18_000, 111, "LOW", 2),
    ]
    monkeypatch.setattr("src.elliott.atr_zigzag", lambda items, config, timeframe=None: sequence if items is structure else [])
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
