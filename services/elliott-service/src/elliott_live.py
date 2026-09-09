from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Candle, Scenario, Timeframe


TIMEFRAME_MILLISECONDS = {
    "M1": 60_000, "M5": 300_000, "M15": 900_000, "M30": 1_800_000,
    "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000,
}


def _snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def normalize_config(value):
    """Accept both the camelCase UI config and snake_case backtest exports."""
    if isinstance(value, dict):
        return {_snake(str(key)): normalize_config(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_config(item) for item in value]
    return value


def _strategy_levels(pattern, config, ec, plan: dict | None = None) -> dict:
    side = 1 if pattern.direction == "LONG" else -1
    p0, p1, p2 = pattern.points["P0"], pattern.points["P1"], pattern.points["P2"]
    wave1 = abs(p1.price - p0.price)
    retracement_a = p1.price - side * wave1 * ec.wave2_min_retracement
    retracement_b = p1.price - side * wave1 * ec.wave2_max_retracement
    levels = {
        "wave1_break": p1.price,
        "wave2_zone_low": min(retracement_a, retracement_b),
        "wave2_zone_high": max(retracement_a, retracement_b),
        "wave2_min_retracement": ec.wave2_min_retracement,
        "wave2_max_retracement": ec.wave2_max_retracement,
        "structure_from": p0.timestamp,
        "structure_to": p2.confirmed_at,
    }
    if not pattern.signal_time or not plan:
        return levels
    levels.update({
        "choch": pattern.features.get("choch_level"),
        "choch_close": pattern.features.get("choch_close"),
        "entry": plan["entry"], "stop": plan["stop"], "targets": plan["targets"],
        "trade_from": pattern.signal_time,
        "trade_to": pattern.signal_time + ec.entry_expiry_bars * TIMEFRAME_MILLISECONDS[ec.entry_timeframe],
    })
    return levels


def _entry_plan(pattern, config, entry: list[dict], entry_pivots: list, available_at: int) -> dict | None:
    """Build the same executable entry setup that the replay evaluates on its next candle."""
    if not pattern.signal_time or not entry:
        return None
    from backtest_core.elliott import _adx, _fixed_rr_target, _rolling, _round_trade_prices, _true_ranges
    from backtest_core.models import DirectionMode, ElliottEntryModel

    ec = config.elliott
    expiry = ec.entry_expiry_bars * TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
    if available_at < pattern.signal_time + config.execution_latency_ms \
            or available_at > pattern.signal_time + expiry:
        return None
    side = 1 if pattern.direction == "LONG" else -1
    allowed = config.direction_mode == DirectionMode.BOTH or config.direction_mode.value == pattern.direction
    if not allowed:
        return None

    duration = TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
    current_index = len(entry) - 1
    current = entry[current_index]
    after_signal = [
        (index, candle) for index, candle in enumerate(entry)
        if int(candle["timestamp"]) + duration >= pattern.signal_time
    ]
    model = ec.entry_model
    order_type = "MARKET"
    candidate_entry = float(current["close"])
    ready = model == ElliottEntryModel.CHOCH_MARKET

    if model == ElliottEntryModel.CHOCH_RETRACE:
        level = pattern.features["choch_level"]
        signal_close = pattern.features["choch_close"]
        candidate_entry = level + side * ec.entry_retracement * abs(signal_close - level)
        order_type, ready = "LIMIT", True
    elif model == ElliottEntryModel.WAVE1_BREAK_RETRACE:
        level = pattern.points["P1"].price
        candidate_entry = level
        ready = any((float(candle["high"]) > level if side == 1 else float(candle["low"]) < level)
                    for _, candle in after_signal if int(candle["timestamp"]) >= pattern.signal_time)
        order_type = "LIMIT"
    elif model == ElliottEntryModel.WAVE1_BREAK_MARKET:
        p1 = pattern.points["P1"]
        threshold = p1.price + side * ec.breakout_buffer_atr * p1.atr
        ready = side * (float(current["close"]) - threshold) > 0 \
            and int(current["timestamp"]) + duration >= pattern.signal_time
    elif model == ElliottEntryModel.WAVE1_BREAK_STOP:
        p1 = pattern.points["P1"]
        candidate_entry = p1.price + side * ec.breakout_buffer_atr * p1.atr
        order_type, ready = "STOP", True
    elif model == ElliottEntryModel.WAVE1_BREAK_RETEST_CONFIRM:
        p1 = pattern.points["P1"].price
        prior = after_signal[:-1]
        broke = any(side * (float(candle["close"]) - p1) > 0 for _, candle in prior)
        zone = ec.retest_zone_atr * pattern.points["P1"].atr
        touched = float(current["low"]) <= p1 + zone if side == 1 else float(current["high"]) >= p1 - zone
        held = side * (float(current["close"]) - p1) >= 0
        directional = side * (float(current["close"]) - float(current["open"])) > 0
        ready = broke and touched and held and directional
    elif model == ElliottEntryModel.MICRO_WAVE3:
        micro = [pivot for pivot in entry_pivots if pattern.signal_time <= pivot.confirmed_at <= available_at
                 and pivot.timestamp >= pattern.points["P2"].timestamp]
        recent = micro[-3:]
        expected = ("LOW", "HIGH", "LOW") if side == 1 else ("HIGH", "LOW", "HIGH")
        ready = len(recent) == 3 and tuple(pivot.kind for pivot in recent) == expected \
            and side * (recent[1].price - recent[0].price) > 0
    elif model == ElliottEntryModel.DISPLACEMENT_RETRACE:
        atr = _rolling(_true_ranges(entry), ec.atr_period)
        impulse = None
        for index, candle in after_signal[-ec.entry_expiry_bars:]:
            candle_range = float(candle["high"]) - float(candle["low"])
            body = side * (float(candle["close"]) - float(candle["open"]))
            if body > 0 and candle_range >= ec.displacement_min_atr * atr[index] \
                    and body / max(candle_range, 1e-12) >= ec.displacement_min_body_ratio:
                impulse = candle
        if impulse:
            body = abs(float(impulse["close"]) - float(impulse["open"]))
            candidate_entry = float(impulse["close"]) - side * ec.displacement_retracement * body
            order_type, ready = "LIMIT", True
    elif model == ElliottEntryModel.P2_LIQUIDITY_SWEEP:
        p2 = pattern.points["P2"].price
        candle_range = float(current["high"]) - float(current["low"])
        wick = (min(float(current["open"]), float(current["close"])) - float(current["low"])
                if side == 1 else float(current["high"]) - max(float(current["open"]), float(current["close"])))
        swept = (float(current["low"]) < p2 < float(current["close"]) if side == 1
                 else float(current["high"]) > p2 > float(current["close"]))
        candidate_entry = float(current["high"]) + config.tick_size if side == 1 else float(current["low"]) - config.tick_size
        order_type = "STOP"
        ready = swept and wick / max(candle_range, 1e-12) >= ec.sweep_min_wick_ratio
    elif model == ElliottEntryModel.WAVE2_TRENDLINE_BREAK:
        kind = "HIGH" if side == 1 else "LOW"
        local = [pivot for pivot in entry_pivots if pivot.kind == kind
                 and pattern.signal_time <= pivot.confirmed_at <= available_at
                 and pivot.timestamp >= pattern.points["P1"].timestamp]
        if current_index > 0 and len(local) >= 2 and local[-1].index != local[-2].index:
            left, right = local[-2], local[-1]
            slope = (right.price - left.price) / (right.index - left.index)
            current_line = left.price + slope * (current_index - left.index)
            previous_line = left.price + slope * (current_index - 1 - left.index)
            ready = side * (float(current["close"]) - current_line) > 0 \
                and side * (float(entry[current_index - 1]["close"]) - previous_line) <= 0
    elif model == ElliottEntryModel.ADX_ACCELERATION:
        adx, plus_di, minus_di = _adx(entry, ec.adx_period)
        if len(entry) >= 3:
            indexes = (len(entry) - 3, len(entry) - 2, len(entry) - 1)
            directional = plus_di[indexes[-1]] > minus_di[indexes[-1]] if side == 1 \
                else minus_di[indexes[-1]] > plus_di[indexes[-1]]
            spreads = [side * (plus_di[index] - minus_di[index]) for index in indexes]
            ready = adx[indexes[2]] > adx[indexes[1]] > adx[indexes[0]] \
                and directional and spreads[2] > spreads[1]
    elif model == ElliottEntryModel.VOLATILITY_EXPANSION:
        true_ranges = _true_ranges(entry)
        atr = _rolling(true_ranges, ec.atr_period)
        long_atr = _rolling(true_ranges, min(ec.atr_period * 3, 500))
        if current_index >= 1:
            directional = side * (float(current["close"]) - float(current["open"])) > 0
            ready = atr[current_index - 1] < long_atr[current_index - 1] and directional \
                and true_ranges[current_index] >= ec.volatility_expansion_ratio * long_atr[current_index]
    elif model == ElliottEntryModel.VOLUME_EXPANSION:
        volume_average = _rolling([float(item.get("volume", 0)) for item in entry], ec.volume_sma_period)
        if current_index >= ec.volume_sma_period:
            candle_range = float(current["high"]) - float(current["low"])
            body = side * (float(current["close"]) - float(current["open"]))
            expanded = float(current.get("volume", 0)) >= ec.volume_expansion_ratio * volume_average[current_index - 1]
            candidate_entry = float(current["high"]) + config.tick_size if side == 1 else float(current["low"]) - config.tick_size
            order_type = "STOP"
            ready = body > 0 and body / max(candle_range, 1e-12) > ec.volume_expansion_min_body_ratio and expanded

    if not ready:
        return None
    stop = pattern.points["P2"].price - side * ec.stop_buffer_atr * pattern.points["P2"].atr
    entry_price, stop, _ = _round_trade_prices(candidate_entry, stop, [], pattern.direction, config.tick_size)
    risk = abs(entry_price - stop)
    targets = [_fixed_rr_target(entry_price, stop, pattern.direction, ec.take_profit_rr)]
    if ec.take_profit_count == 2:
        targets.append(_fixed_rr_target(entry_price, stop, pattern.direction, ec.second_take_profit_rr))
    _, _, targets = _round_trade_prices(entry_price, stop, targets, pattern.direction, config.tick_size)
    rr = side * (targets[0] - entry_price) / max(risk, 1e-12)
    stop_on_loss_side = stop < entry_price if side == 1 else stop > entry_price
    if risk <= 0 or rr < ec.minimum_rr or not stop_on_loss_side:
        return None
    return {
        "entry": entry_price, "entry_type": order_type, "stop": stop, "targets": targets,
        "target_rrs": [ec.take_profit_rr] + ([ec.second_take_profit_rr] if ec.take_profit_count == 2 else []),
    }


@dataclass
class ElliottLiveEngine:
    emitted: set[str] = field(default_factory=set)
    live_signal_ids: set[str] = field(default_factory=set)
    latest_patterns: dict[str, list[dict]] = field(default_factory=dict)
    latest_entries: dict[str, list[dict]] = field(default_factory=dict)

    def generate(self, symbol: str, current: Candle, candles_by_tf: dict, raw_config: dict,
                 allow_live_emit: bool = True) -> list[Scenario]:
        # The live image imports the exact detector and config models used by
        # backtests, so changes cannot silently create strategy drift.
        from backtest_core.elliott import detect_patterns
        from backtest_core.models import BacktestConfig

        config = BacktestConfig.model_validate(normalize_config(raw_config))
        if str(config.strategy) != "ELLIOTT":
            return []
        ec = config.elliott
        if str(current.timeframe) != ec.entry_timeframe:
            return []
        required = (ec.structure_timeframe, ec.entry_timeframe, ec.macro_timeframe)
        if any(not candles_by_tf.get((symbol, Timeframe(item))) for item in required):
            return []
        series = {
            item: [candle.model_dump(mode="json") for candle in candles_by_tf[(symbol, Timeframe(item))]]
            for item in required
        }
        patterns, _, entry_pivots = detect_patterns(series[ec.structure_timeframe], series[ec.entry_timeframe],
                                                     series[ec.macro_timeframe], ec)
        entry = series[ec.entry_timeframe]
        available_at = current.timestamp + TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        plans = {pattern.id: plan for pattern in patterns
                 if (plan := _entry_plan(pattern, config, entry, entry_pivots, available_at)) is not None}
        self.latest_patterns[symbol] = [
            {
                "id": pattern.id, "direction": pattern.direction, "state": pattern.state,
                "invalid_reason": pattern.invalid_reason, "signal_time": pattern.signal_time,
                "structure_timeframe": ec.structure_timeframe,
                "entry_timeframe": ec.entry_timeframe,
                "strategy_levels": _strategy_levels(pattern, config, ec, plans.get(pattern.id)),
                "points": {
                    label: {
                        "timestamp": point.timestamp, "confirmed_at": point.confirmed_at,
                        "price": point.price, "kind": point.kind,
                    }
                    for label, point in pattern.points.items()
                },
            }
            for pattern in patterns
        ]
        expiry = ec.entry_expiry_bars * TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        entries = []
        for pattern in patterns:
            plan = plans.get(pattern.id)
            if not pattern.signal_time or not plan:
                continue
            entries.append({
                "id":pattern.id,"direction":pattern.direction,"setup_type":"ELLIOTT_WAVE3",
                "status":"ACTIVE" if pattern.signal_time+expiry >= available_at else "EXPIRED",
                "entry_type":plan["entry_type"],"entry_zone_low":plan["entry"],"entry_zone_high":plan["entry"],
                "created_at":pattern.signal_time,"expires_at":pattern.signal_time+expiry,
                "entry_model":str(ec.entry_model),
                "origin":"LIVE" if pattern.id in self.live_signal_ids else "HISTORICAL",
                "stop_loss_price":plan["stop"],"take_profit_prices":plan["targets"],
            })
        self.latest_entries[symbol]=entries
        if not allow_live_emit:
            return []
        result = []
        for pattern in sorted((item for item in patterns if item.signal_time), key=lambda item: item.signal_time):
            plan = plans.get(pattern.id)
            if pattern.id in self.emitted or not plan:
                continue
            allocations = [1.0] if ec.take_profit_count == 1 else list(ec.take_profit_allocations)
            first_take_action = str(ec.first_take_action)
            break_even = "ONE_R" if ec.break_even_at_one_r else (
                "AFTER_TARGET" if first_take_action == "MOVE_TO_BREAK_EVEN" else "OFF"
            )
            self.emitted.add(pattern.id)
            self.live_signal_ids.add(pattern.id)
            for item in entries:
                if item["id"] == pattern.id:
                    item["origin"] = "LIVE"
                    break
            result.append(Scenario(
                id=pattern.id, symbol=symbol, timeframe=Timeframe(ec.entry_timeframe),
                direction=pattern.direction, setup_type="ELLIOTT_WAVE3", confidence=1,
                entry_zone_low=plan["entry"], entry_zone_high=plan["entry"], entry_type=plan["entry_type"],
                stop_loss_price=plan["stop"], take_profit_prices=plan["targets"], target_allocations=allocations,
                target_rrs=plan["target_rrs"],
                break_even_rule=break_even,
                move_stop_to_break_even_after_target=1 if break_even == "AFTER_TARGET" else None,
                one_trade_per_zone=True, deduplication_key=f"ELLIOTT:{pattern.id}",
                reasons=["Elliott Wave 2 confirmed", "Wave 3 CHOCH confirmed"],
                objects_used=[{"kind": "ELLIOTT_PATTERN", "id": pattern.id}],
                created_at=available_at, expires_at=pattern.signal_time + expiry,
            ))
        return result
