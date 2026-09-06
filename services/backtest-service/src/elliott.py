from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, floor, sqrt
from statistics import mean, pstdev
from .performance import extended_performance
from uuid import NAMESPACE_URL, uuid5

from .models import BacktestConfig, DirectionMode, ElliottEntryModel, ElliottMacroFilter

TIMEFRAME_MILLISECONDS = {
    "M1": 60_000, "M5": 300_000, "M15": 900_000, "M30": 1_800_000,
    "H1": 3_600_000, "H4": 14_400_000, "D1": 86_400_000,
}


@dataclass(frozen=True)
class Pivot:
    index: int
    timestamp: int
    confirmed_at: int
    price: float
    kind: str
    atr: float


@dataclass
class Pattern:
    id: str
    direction: str
    points: dict[str, Pivot]
    state: str
    features: dict = field(default_factory=dict)
    invalid_reason: str | None = None
    signal_time: int | None = None


def _true_ranges(candles: list[dict]) -> list[float]:
    result: list[float] = []
    previous = None
    for candle in candles:
        high, low = float(candle["high"]), float(candle["low"])
        result.append(high - low if previous is None else max(high - low, abs(high - previous), abs(low - previous)))
        previous = float(candle["close"])
    return result


def _rolling(values: list[float], period: int) -> list[float]:
    result, total = [], 0.0
    for index, value in enumerate(values):
        total += value
        if index >= period:
            total -= values[index - period]
        result.append(total / min(index + 1, period))
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha, result = 2 / (period + 1), [values[0]]
    for value in values[1:]:
        result.append(value * alpha + result[-1] * (1 - alpha))
    return result


def _adx(candles: list[dict], period: int) -> tuple[list[float], list[float], list[float]]:
    if not candles:
        return [], [], []
    trs = _true_ranges(candles)
    plus_dm, minus_dm = [0.0], [0.0]
    for index in range(1, len(candles)):
        up = float(candles[index]["high"]) - float(candles[index - 1]["high"])
        down = float(candles[index - 1]["low"]) - float(candles[index]["low"])
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr, plus_avg, minus_avg = _rolling(trs, period), _rolling(plus_dm, period), _rolling(minus_dm, period)
    plus_di = [100 * value / tr if tr else 0 for value, tr in zip(plus_avg, atr)]
    minus_di = [100 * value / tr if tr else 0 for value, tr in zip(minus_avg, atr)]
    dx = [100 * abs(left - right) / (left + right) if left + right else 0 for left, right in zip(plus_di, minus_di)]
    return _rolling(dx, period), plus_di, minus_di


def atr_zigzag(candles: list[dict], config, timeframe: str | None = None) -> list[Pivot]:
    """ATR ZigZag whose pivot timestamp is separate from its later confirmation time."""
    if len(candles) < 3:
        return []
    atrs = _rolling(_true_ranges(candles), config.atr_period)
    direction = 0
    high_index = low_index = 0
    pivots: list[Pivot] = []
    candle_duration = TIMEFRAME_MILLISECONDS[timeframe or config.structure_timeframe]

    def append(index: int, confirmed: int, kind: str):
        price = float(candles[index]["high" if kind == "HIGH" else "low"])
        if pivots and (pivots[-1].kind == kind or index - pivots[-1].index < config.min_swing_candles):
            if pivots and pivots[-1].kind == kind:
                better = price > pivots[-1].price if kind == "HIGH" else price < pivots[-1].price
                if better:
                    pivots[-1] = Pivot(
                        index, int(candles[index]["timestamp"]),
                        int(candles[confirmed]["timestamp"]) + candle_duration, price, kind, atrs[index],
                    )
            return
        if pivots:
            distance = abs(price - pivots[-1].price)
            if distance < config.min_swing_atr * max(atrs[index], 1e-12):
                return
            if config.max_swing_candles and index - pivots[-1].index > config.max_swing_candles:
                return
        pivots.append(Pivot(
            index, int(candles[index]["timestamp"]),
            int(candles[confirmed]["timestamp"]) + candle_duration, price, kind, atrs[index],
        ))

    for index in range(1, len(candles)):
        if float(candles[index]["high"]) >= float(candles[high_index]["high"]):
            high_index = index
        if float(candles[index]["low"]) <= float(candles[low_index]["low"]):
            low_index = index
        threshold = config.zigzag_reversal_atr * max(atrs[index], 1e-12)
        if direction == 0:
            if float(candles[high_index]["high"]) - float(candles[index]["low"]) >= threshold and high_index < index:
                append(low_index if low_index < high_index else 0, high_index, "LOW")
                append(high_index, index, "HIGH")
                direction, low_index = -1, index
            elif float(candles[index]["high"]) - float(candles[low_index]["low"]) >= threshold and low_index < index:
                append(high_index if high_index < low_index else 0, low_index, "HIGH")
                append(low_index, index, "LOW")
                direction, high_index = 1, index
        elif direction == 1 and float(candles[high_index]["high"]) - float(candles[index]["low"]) >= threshold:
            append(high_index, index, "HIGH")
            direction, low_index = -1, index
        elif direction == -1 and float(candles[index]["high"]) - float(candles[low_index]["low"]) >= threshold:
            append(low_index, index, "LOW")
            direction, high_index = 1, index
    return pivots


def _efficiency(candles: list[dict], left: int, right: int) -> float:
    closes = [float(item["close"]) for item in candles[left:right + 1]]
    path = sum(abs(closes[index] - closes[index - 1]) for index in range(1, len(closes)))
    return abs(closes[-1] - closes[0]) / path if path else 0


def _macro_direction(candles: list[dict], timestamp: int, mode: ElliottMacroFilter, timeframe: str) -> str:
    duration = TIMEFRAME_MILLISECONDS[timeframe]
    available = [item for item in candles if int(item["timestamp"]) + duration <= timestamp]
    required = 200 if mode in (ElliottMacroFilter.EMA200, ElliottMacroFilter.EMA_CROSS) else 3
    if mode == ElliottMacroFilter.OFF or len(available) < required:
        return "BOTH"
    closes = [float(item["close"]) for item in available]
    if mode == ElliottMacroFilter.EMA200:
        return "LONG" if closes[-1] >= _ema(closes, 200)[-1] else "SHORT"
    if mode == ElliottMacroFilter.EMA_CROSS:
        return "LONG" if _ema(closes, 50)[-1] >= _ema(closes, 200)[-1] else "SHORT"
    return "LONG" if closes[-1] >= closes[max(0, len(closes) - 3)] else "SHORT"


def detect_patterns(structure: list[dict], entry: list[dict], macro: list[dict], config) -> tuple[list[Pattern], list[Pivot], list[Pivot]]:
    pivots = atr_zigzag(structure, config, config.structure_timeframe)
    entry_pivots = atr_zigzag(entry, config, config.entry_timeframe)
    adx, plus_di, minus_di = _adx(entry, config.adx_period)
    entry_atr = _rolling(_true_ranges(entry), config.atr_period)
    volume_avg = _rolling([float(item.get("volume", 0)) for item in entry], config.volume_sma_period)
    patterns: list[Pattern] = []
    seen: set[tuple[int, int, int]] = set()
    for pos in range(2, len(pivots)):
        p0, p1, p2 = pivots[pos - 2:pos + 1]
        if (p0.kind, p1.kind, p2.kind) == ("LOW", "HIGH", "LOW"):
            direction, sign = "LONG", 1
        elif (p0.kind, p1.kind, p2.kind) == ("HIGH", "LOW", "HIGH"):
            direction, sign = "SHORT", -1
        else:
            continue
        key = (p0.timestamp, p1.timestamp, p2.timestamp)
        if key in seen:
            continue
        seen.add(key)
        length = abs(p1.price - p0.price)
        duration = p1.index - p0.index
        retracement = abs(p2.price - p1.price) / length if length else 99
        time_ratio = (p2.index - p1.index) / max(duration, 1)
        efficiency = _efficiency(structure, p0.index, p1.index)
        features = {"wave1_atr": length / max(p1.atr, 1e-12), "wave1_efficiency": efficiency,
                    "wave1_candles": duration, "wave2_retracement": retracement, "wave2_time_ratio": time_ratio}
        identity = f"{direction}:{p0.timestamp}:{p1.timestamp}:{p2.timestamp}"
        pattern = Pattern(str(uuid5(NAMESPACE_URL, identity)), direction,
                          {"P0": p0, "P1": p1, "P2": p2}, "WAVE2_CONFIRMED", features)
        invalid = None
        if sign * (p2.price - p0.price) <= 0:
            invalid = "WAVE2_BEYOND_P0"
        elif features["wave1_atr"] < config.wave1_min_atr or duration < config.wave1_min_candles:
            invalid = "WAVE1_TOO_SMALL"
        elif config.wave1_max_candles and duration > config.wave1_max_candles:
            invalid = "WAVE1_TOO_LONG"
        elif efficiency < config.wave1_min_efficiency:
            invalid = "WAVE1_LOW_EFFICIENCY"
        elif not config.wave2_min_retracement <= retracement <= config.wave2_max_retracement:
            invalid = "WAVE2_RETRACEMENT"
        elif not config.wave2_min_time_ratio <= time_ratio <= config.wave2_max_time_ratio:
            invalid = "WAVE2_TIME_RATIO"
        if config.require_bos and pos >= 3:
            prior = pivots[pos - 3]
            if sign * (p1.price - prior.price) <= config.bos_buffer_atr * p1.atr:
                invalid = "WAVE1_NO_BOS"
        macro_side = _macro_direction(macro, p2.confirmed_at, config.macro_filter, config.macro_timeframe)
        features["macro_direction"] = macro_side
        if macro_side not in ("BOTH", direction):
            invalid = "MACRO_FILTER"
        if invalid:
            pattern.state, pattern.invalid_reason = "INVALID", invalid
            patterns.append(pattern)
            continue

        # A Wave 3 entry belongs to the move out of P2. Once the next structure
        # pivot in the Wave 3 direction is confirmed, that move is complete and
        # a later CHOCH must not revive this old pattern.
        expected_p3_kind = "HIGH" if direction == "LONG" else "LOW"
        p3_candidate = next(
            (pivot for pivot in pivots if pivot.index > p2.index and pivot.kind == expected_p3_kind),
            None,
        )
        signal_deadline = p3_candidate.confirmed_at if p3_candidate else None
        pattern.features["signal_deadline"] = signal_deadline or 0
        entry_duration = TIMEFRAME_MILLISECONDS[config.entry_timeframe]
        candidates = [
            (index, candle) for index, candle in enumerate(entry)
            if int(candle["timestamp"]) >= p2.confirmed_at
            and (signal_deadline is None or int(candle["timestamp"]) + entry_duration < signal_deadline)
        ]
        trigger = None
        for index, candle in candidates:
            if index + 1 < max(config.atr_period, config.adx_period, config.volume_sma_period):
                continue
            candle_available_at = int(candle["timestamp"]) + entry_duration
            prior_swings = [
                pivot for pivot in entry_pivots
                if pivot.confirmed_at <= int(candle["timestamp"]) and pivot.timestamp >= p1.timestamp
            ]
            relevant = [pivot for pivot in prior_swings if pivot.kind == ("HIGH" if direction == "LONG" else "LOW")]
            if not relevant:
                continue
            level = relevant[-1].price
            close, open_price = float(candle["close"]), float(candle["open"])
            crossed = close > level if direction == "LONG" else close < level
            displacement = abs(close - level) / max(entry_atr[index], 1e-12)
            body = abs(close - open_price) / max(float(candle["high"]) - float(candle["low"]), 1e-12)
            volume_ratio = float(candle.get("volume", 0)) / max(volume_avg[index], 1e-12)
            di_ok = plus_di[index] > minus_di[index] if direction == "LONG" else minus_di[index] > plus_di[index]
            if crossed and displacement >= config.choch_min_atr and body >= config.choch_min_body_ratio \
                    and adx[index] >= config.adx_min and (not config.require_di_confirmation or di_ok) \
                    and volume_ratio >= config.min_volume_ratio:
                trigger = (index, candle, level, displacement, body, volume_ratio)
                break
        if trigger:
            index, candle, level, displacement, body, volume_ratio = trigger
            pattern.state, pattern.signal_time = "WAVE3_POTENTIAL", int(candle["timestamp"]) + entry_duration
            pattern.features.update({"choch_level": level, "choch_displacement_atr": displacement,
                                     "choch_close": close,
                                     "choch_body_ratio": body, "adx": adx[index], "plus_di": plus_di[index],
                                     "minus_di": minus_di[index], "volume_ratio": volume_ratio})
        patterns.append(pattern)

    # Extend non-overlapping candidates to W3/W4/W5 and then an elementary ABC zigzag.
    for pattern in patterns:
        if pattern.state == "INVALID":
            continue
        p2 = pattern.points["P2"]
        later = [pivot for pivot in pivots if pivot.index > p2.index]
        expected = "HIGH" if pattern.direction == "LONG" else "LOW"
        sequence = [pivot for pivot in later if pivot.kind == expected]
        if sequence:
            p3 = sequence[0]
            broke = p3.price > pattern.points["P1"].price if pattern.direction == "LONG" else p3.price < pattern.points["P1"].price
            if broke:
                pattern.points["P3"], pattern.state = p3, "WAVE3_CONFIRMED"
                after3 = [pivot for pivot in later if pivot.index > p3.index]
                if after3:
                    p4 = after3[0]
                    overlap = p4.price <= pattern.points["P1"].price if pattern.direction == "LONG" else p4.price >= pattern.points["P1"].price
                    if overlap:
                        pattern.invalid_reason = "WAVE4_OVERLAPS_WAVE1"
                    else:
                        pattern.points["P4"] = p4
                        after4 = [pivot for pivot in after3 if pivot.index > p4.index]
                        if after4:
                            p5 = after4[0]
                            pattern.points["P5"], pattern.state = p5, "IMPULSE_COMPLETE"
                            lengths = [abs(pattern.points["P1"].price - pattern.points["P0"].price),
                                       abs(p3.price - p2.price), abs(p5.price - p4.price)]
                            if lengths[1] < min(lengths[0], lengths[2]):
                                pattern.state, pattern.invalid_reason = "INVALID", "WAVE3_SHORTEST"
                            correction = [pivot for pivot in after4 if pivot.index > p5.index][:3]
                            if len(correction) == 3:
                                pattern.points.update(dict(zip(("A", "B", "C"), correction)))
                                pattern.state = "ABC_COMPLETE"
                                pattern.features["correction_type"] = "ZIGZAG_ABC"
    return patterns, pivots, entry_pivots


def _point(value: Pivot) -> dict:
    return {"index": value.index, "timestamp": value.timestamp, "confirmed_at": value.confirmed_at,
            "price": value.price, "kind": value.kind, "atr": value.atr}


def _fixed_rr_target(entry_price: float, stop: float, direction: str, take_profit_rr: float) -> float:
    """Place the Elliott exit at a fixed multiple of the actual stop distance."""
    side = 1 if direction == "LONG" else -1
    return entry_price + side * abs(entry_price - stop) * take_profit_rr


def _fee_adjusted_break_even_stop(entry_price: float, direction: str, maker_fee: float,
                                  taker_fee: float, slippage: float, tick_size: float,
                                  funding_per_unit: float = 0) -> float:
    """Return a trigger whose simulated fill covers both commissions and exit slippage."""
    if direction == "LONG":
        executed = (entry_price * (1 + maker_fee) + funding_per_unit) / (1 - taker_fee)
        raw = executed / (1 - slippage)
        return ceil(raw / tick_size) * tick_size
    executed = (entry_price * (1 - maker_fee) - funding_per_unit) / (1 + taker_fee)
    raw = executed / (1 + slippage)
    return floor(raw / tick_size) * tick_size


def _liquidation_price(position: dict, config: BacktestConfig, taker_fee: float) -> float:
    """Price where remaining margin reaches maintenance margin after all costs."""
    # After a partial take-profit the released quantity no longer consumes
    # margin and must not dilute costs carried by the remaining position.
    quantity = position.get("remaining", position["quantity"])
    entry = position["entry_price"]
    margin = entry * quantity / config.leverage
    maintenance = entry * quantity * config.maintenance_margin_percent / 100
    entry_cost = entry * quantity * position["entry_fee_rate"]
    exit_cost_rate = taker_fee + config.liquidation_fee_percent / 100
    funding = position["funding"]
    if position["direction"] == "LONG":
        return (entry * quantity - margin + maintenance + entry_cost + funding) / max(
            quantity * (1 - exit_cost_rate), 1e-12,
        )
    return (entry * quantity + margin - maintenance - entry_cost - funding) / max(
        quantity * (1 + exit_cost_rate), 1e-12,
    )


def _elliott_position_quantity(capital: float, initial_capital: float, entry_price: float,
                               stop_price: float, risk_percent: float, position_size_percent: float,
                               use_margin: bool, leverage: float, reinvest_profits: bool,
                               lot_size: float) -> float:
    sizing_capital = capital if reinvest_profits else min(initial_capital, capital)
    unit_risk = abs(entry_price - stop_price)
    if unit_risk <= 0:
        return 0
    # Elliott owns the full capital assigned to the asset. The generic
    # position_size_percent setting is not exposed for this strategy and must
    # not silently reduce its margin capacity (its legacy default is 25%).
    allocation = sizing_capital
    capacity_quantity = allocation * (leverage if use_margin else 1) / entry_price
    if risk_percent == 0:
        return capacity_quantity
    risk_quantity = sizing_capital * risk_percent / 100 / unit_risk
    return min(risk_quantity, capacity_quantity)


def _round_trade_prices(entry: float, stop: float, targets: list[float], direction: str,
                        tick_size: float) -> tuple[float, float, list[float]]:
    entry = round(entry / tick_size) * tick_size
    if direction == "LONG":
        stop = floor(stop / tick_size) * tick_size
        targets = [ceil(target / tick_size) * tick_size for target in targets]
    else:
        stop = ceil(stop / tick_size) * tick_size
        targets = [floor(target / tick_size) * tick_size for target in targets]
    return entry, stop, targets


def run_elliott_replay(candles_by_tf: dict[str, list[dict]], config: BacktestConfig,
                       evaluation_start: int | None = None) -> dict:
    ec = config.elliott
    structure = sorted(candles_by_tf[ec.structure_timeframe], key=lambda item: item["timestamp"])
    entry = sorted(candles_by_tf[ec.entry_timeframe], key=lambda item: item["timestamp"])
    macro = sorted(candles_by_tf[ec.macro_timeframe], key=lambda item: item["timestamp"])
    if not entry:
        raise ValueError(f"no Elliott entry candles for {ec.entry_timeframe}")
    patterns, structure_pivots, entry_pivots = detect_patterns(structure, entry, macro, ec)
    entry_true_ranges = _true_ranges(entry)
    entry_atr = _rolling(entry_true_ranges, ec.atr_period)
    entry_long_atr = _rolling(entry_true_ranges, min(ec.atr_period * 3, 500))
    entry_adx, entry_plus_di, entry_minus_di = _adx(entry, ec.adx_period)
    entry_volume_average = _rolling([float(item.get("volume", 0)) for item in entry], ec.volume_sma_period)
    signals = sorted([item for item in patterns if item.signal_time], key=lambda item: item.signal_time)
    maker_fee = (config.maker_fee_percent if config.maker_fee_percent is not None else config.fee_percent) / 100
    taker_fee = (config.taker_fee_percent if config.taker_fee_percent is not None else config.fee_percent) / 100
    slip = config.slippage_percent / 100
    capital, trades, equity = config.initial_capital, [], []
    processed: set[str] = set()
    traded: set[str] = set()
    wave1_broken: set[str] = set()
    expired_signals = 0
    position = None

    def activate_one_r_break_even(candle_high: float, candle_low: float):
        if not position or not ec.break_even_at_one_r or position["break_even_active"]:
            return
        side = 1 if position["direction"] == "LONG" else -1
        one_r = position["entry_price"] + side * abs(position["entry_price"] - position["initial_stop"])
        reached = candle_high >= one_r if side == 1 else candle_low <= one_r
        if reached:
            position["stop"] = _fee_adjusted_break_even_stop(
                position["entry_price"], position["direction"], position["entry_fee_rate"],
                taker_fee, slip, config.tick_size, position["funding"] / max(position["remaining"], 1e-12),
            )
            position["break_even_active"] = True

    def finish(raw_price: float, timestamp: int, reason: str, quantity: float | None = None):
        nonlocal capital, position
        side = 1 if position["direction"] == "LONG" else -1
        quantity = position["remaining"] if quantity is None else min(quantity, position["remaining"])
        exit_price = raw_price if reason == "FIXED_RR_TARGET" else raw_price * (1 - slip * side)
        gross = (exit_price - position["entry_price"]) * quantity * side
        exit_fee_rate = maker_fee if reason == "FIXED_RR_TARGET" else taker_fee
        fees = (position["entry_price"] * quantity * position["entry_fee_rate"]
                + exit_price * quantity * exit_fee_rate)
        liquidation_fee = (exit_price * quantity * config.liquidation_fee_percent / 100
                           if reason == "LIQUIDATION" else 0)
        pnl = gross - fees - liquidation_fee
        capital += pnl
        position["realized"] += pnl
        position["fees"] += fees + liquidation_fee
        position["remaining"] -= quantity
        position["exits"].append({
            "timestamp": timestamp, "price": exit_price, "quantity": quantity,
            "pnl": pnl, "fees": fees + liquidation_fee, "reason": reason,
        })
        if position["remaining"] > 1e-12:
            return
        trades.append({**position, "id": len(trades) + 1, "exit_time": timestamp, "exit_price": exit_price,
                       # Report return on position margin, consistently with
                       # portfolio reports (not return on risk budget).
                       "pnl": position["realized"],
                       "pnl_percent": position["realized"] / max(
                           position["entry_price"] * position["quantity"] / (config.leverage if ec.use_margin else 1), 1e-12,
                       ) * 100,
                       "fees": position["fees"], "funding": position["funding"], "reason": reason})
        for key in ("stop", "targets", "target_allocations", "risk_capital", "remaining", "realized",
                    "break_even_active", "entry_fee_rate", "last_funding_time"):
            trades[-1].pop(key, None)
        position = None

    for candle_index, candle in enumerate(entry):
        timestamp = int(candle["timestamp"])
        available_at = timestamp + TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        if evaluation_start is not None and timestamp < evaluation_start:
            continue
        high, low, close = float(candle["high"]), float(candle["low"]), float(candle["close"])
        had_position = position is not None
        if position:
            interval = config.funding_interval_hours * 3_600_000
            funding_events = max(0, (available_at - position["last_funding_time"]) // interval)
            if funding_events:
                funding = (
                    position["entry_price"] * position["remaining"] * config.funding_percent_per_day / 100
                    * config.funding_interval_hours / 24 * funding_events
                )
                signed_funding = funding * (1 if position["direction"] == "LONG" else -1)
                capital -= signed_funding
                position["realized"] -= signed_funding
                position["funding"] += signed_funding
                position["last_funding_time"] += funding_events * interval
            side = 1 if position["direction"] == "LONG" else -1
            liquidation = _liquidation_price(position, config, taker_fee)
            margin_active = ec.use_margin and config.leverage > 1
            terminal = (max(position["stop"], liquidation) if side == 1 else min(position["stop"], liquidation)) \
                if margin_active else position["stop"]
            terminal_hit = low <= terminal if side == 1 else high >= terminal
            gap_through_liquidation = (float(candle["open"]) <= liquidation if side == 1
                                       else float(candle["open"]) >= liquidation)
            liquidation_first = margin_active and (terminal == liquidation or gap_through_liquidation)
            if terminal_hit:
                reason = ("LIQUIDATION" if liquidation_first else
                          "BREAK_EVEN" if position["break_even_active"] else "STRUCTURAL_STOP")
                raw_terminal = min(float(candle["open"]), terminal) if side == 1 else max(float(candle["open"]), terminal)
                finish(raw_terminal, timestamp, reason)
            else:
                reached = [target for target in position["targets"] if high >= target] if side == 1 else [target for target in position["targets"] if low <= target]
                for target in reached:
                    target_index = position["targets"].index(target)
                    position["targets"].pop(target_index)
                    allocation = position["target_allocations"].pop(target_index)
                    is_final = not position["targets"]
                    if is_final or ec.first_take_action.value == "PARTIAL_CLOSE":
                        finish(target, timestamp, "FIXED_RR_TARGET",
                               position["remaining"] if is_final else position["quantity"] * allocation)
                    if position and not is_final and ec.first_take_action.value == "MOVE_TO_BREAK_EVEN":
                        position["stop"] = _fee_adjusted_break_even_stop(
                            position["entry_price"], position["direction"], position["entry_fee_rate"],
                            taker_fee, slip, config.tick_size, position["funding"] / max(position["remaining"], 1e-12),
                        )
                        position["break_even_active"] = True
                activate_one_r_break_even(high, low)
        if position is None and not had_position:
            expiry_ms = ec.entry_expiry_bars * TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
            available = [
                item for item in signals
                if item.id not in processed and item.signal_time + config.execution_latency_ms <= timestamp
            ]
            for stale in [item for item in available if timestamp > item.signal_time + expiry_ms]:
                processed.add(stale.id)
                expired_signals += 1
            eligible = [item for item in available if item.id not in processed]
            selected = None
            for candidate in eligible:
                candidate_side = 1 if candidate.direction == "LONG" else -1
                entry_duration = TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
                previous_after_signal = candle_index > 0 \
                    and int(entry[candle_index - 1]["timestamp"]) + entry_duration >= candidate.signal_time
                candidate_entry = float(candle["open"]) * (1 + slip * candidate_side)
                candidate_fee = taker_fee
                touched = timestamp >= candidate.signal_time
                if ec.entry_model == ElliottEntryModel.CHOCH_RETRACE:
                    level = candidate.features["choch_level"]
                    signal_close = candidate.features["choch_close"]
                    candidate_entry = level + candidate_side * ec.entry_retracement * abs(signal_close - level)
                    candidate_entry = round(candidate_entry / config.tick_size) * config.tick_size
                    candidate_fee = maker_fee
                    touched = timestamp >= candidate.signal_time and low <= candidate_entry <= high
                elif ec.entry_model == ElliottEntryModel.WAVE1_BREAK_RETRACE:
                    level = candidate.points["P1"].price
                    candidate_entry = round(level / config.tick_size) * config.tick_size
                    candidate_fee = maker_fee
                    if candidate.id not in wave1_broken:
                        broke = high > level if candidate_side == 1 else low < level
                        if broke:
                            wave1_broken.add(candidate.id)
                        # Break and retrace order is unknowable inside one OHLC
                        # candle, so a fill is allowed only on a later candle.
                        continue
                    touched = low <= candidate_entry <= high
                elif ec.entry_model == ElliottEntryModel.WAVE1_BREAK_MARKET:
                    threshold = candidate.points["P1"].price + candidate_side * ec.breakout_buffer_atr * candidate.points["P1"].atr
                    previous_close = float(entry[candle_index - 1]["close"]) if candle_index else candidate_entry
                    touched = previous_after_signal and candidate_side * (previous_close - threshold) > 0
                elif ec.entry_model == ElliottEntryModel.WAVE1_BREAK_STOP:
                    candidate_entry = candidate.points["P1"].price + candidate_side * ec.breakout_buffer_atr * candidate.points["P1"].atr
                    candidate_entry = round(candidate_entry / config.tick_size) * config.tick_size
                    touched = high >= candidate_entry if candidate_side == 1 else low <= candidate_entry
                elif ec.entry_model == ElliottEntryModel.WAVE1_BREAK_RETEST_CONFIRM:
                    p1 = candidate.points["P1"].price
                    start = max(0, candle_index - ec.entry_expiry_bars)
                    closed = [item for item in entry[start:candle_index]
                              if int(item["timestamp"]) + entry_duration >= candidate.signal_time]
                    broke = any(candidate_side * (float(item["close"]) - p1) > 0 for item in closed[:-1])
                    previous = closed[-1] if closed else None
                    if previous:
                        zone = ec.retest_zone_atr * candidate.points["P1"].atr
                        touched_zone = float(previous["low"]) <= p1 + zone if candidate_side == 1 else float(previous["high"]) >= p1 - zone
                        held = candidate_side * (float(previous["close"]) - p1) >= 0
                        directional = candidate_side * (float(previous["close"]) - float(previous["open"])) > 0
                        touched = broke and touched_zone and held and directional
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.MICRO_WAVE3:
                    micro = [pivot for pivot in entry_pivots if candidate.signal_time <= pivot.confirmed_at <= timestamp
                             and pivot.timestamp >= candidate.points["P2"].timestamp]
                    recent = micro[-3:]
                    kinds = tuple(pivot.kind for pivot in recent)
                    expected = ("LOW", "HIGH", "LOW") if candidate_side == 1 else ("HIGH", "LOW", "HIGH")
                    touched = len(recent) == 3 and kinds == expected and candidate_side * (recent[1].price - recent[0].price) > 0
                elif ec.entry_model == ElliottEntryModel.DISPLACEMENT_RETRACE:
                    impulse = None
                    for index in range(max(0, candle_index - ec.entry_expiry_bars), candle_index):
                        item = entry[index]
                        if int(item["timestamp"]) + entry_duration < candidate.signal_time:
                            continue
                        candle_range = float(item["high"]) - float(item["low"])
                        body = candidate_side * (float(item["close"]) - float(item["open"]))
                        if (body > 0 and candle_range >= ec.displacement_min_atr * entry_atr[index]
                                and body / max(candle_range, 1e-12) >= ec.displacement_min_body_ratio):
                            impulse = item
                    if impulse:
                        body = abs(float(impulse["close"]) - float(impulse["open"]))
                        candidate_entry = float(impulse["close"]) - candidate_side * ec.displacement_retracement * body
                        candidate_entry = round(candidate_entry / config.tick_size) * config.tick_size
                        candidate_fee = maker_fee
                        touched = low <= candidate_entry <= high
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.P2_LIQUIDITY_SWEEP:
                    previous = entry[candle_index - 1] if candle_index else None
                    if previous and previous_after_signal:
                        p2 = candidate.points["P2"].price
                        candle_range = float(previous["high"]) - float(previous["low"])
                        wick = (min(float(previous["open"]), float(previous["close"])) - float(previous["low"])
                                if candidate_side == 1 else float(previous["high"]) - max(float(previous["open"]), float(previous["close"])))
                        swept = float(previous["low"]) < p2 and float(previous["close"]) > p2 if candidate_side == 1 else float(previous["high"]) > p2 and float(previous["close"]) < p2
                        candidate_entry = float(previous["high"]) + config.tick_size if candidate_side == 1 else float(previous["low"]) - config.tick_size
                        candidate_entry = round(candidate_entry / config.tick_size) * config.tick_size
                        touched = swept and wick / max(candle_range, 1e-12) >= ec.sweep_min_wick_ratio \
                            and (high >= candidate_entry if candidate_side == 1 else low <= candidate_entry)
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.WAVE2_TRENDLINE_BREAK:
                    kind = "HIGH" if candidate_side == 1 else "LOW"
                    local = [pivot for pivot in entry_pivots if pivot.kind == kind
                             and candidate.signal_time <= pivot.confirmed_at <= timestamp
                             and pivot.timestamp >= candidate.points["P1"].timestamp]
                    if candle_index > 1 and len(local) >= 2 and local[-1].index != local[-2].index:
                        left, right = local[-2], local[-1]
                        slope = (right.price - left.price) / (right.index - left.index)
                        previous_line = left.price + slope * (candle_index - 1 - left.index)
                        earlier_line = left.price + slope * (candle_index - 2 - left.index)
                        touched = candidate_side * (float(entry[candle_index - 1]["close"]) - previous_line) > 0 \
                            and candidate_side * (float(entry[candle_index - 2]["close"]) - earlier_line) <= 0
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.ADX_ACCELERATION:
                    if candle_index >= 4 and previous_after_signal:
                        indexes = (candle_index - 3, candle_index - 2, candle_index - 1)
                        directional = (entry_plus_di[indexes[-1]] > entry_minus_di[indexes[-1]] if candidate_side == 1
                                       else entry_minus_di[indexes[-1]] > entry_plus_di[indexes[-1]])
                        spreads = [candidate_side * (entry_plus_di[index] - entry_minus_di[index]) for index in indexes]
                        touched = entry_adx[indexes[2]] > entry_adx[indexes[1]] > entry_adx[indexes[0]] \
                            and directional and spreads[2] > spreads[1]
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.VOLATILITY_EXPANSION:
                    previous = candle_index - 1
                    if previous >= 2 and previous_after_signal:
                        directional = candidate_side * (float(entry[previous]["close"]) - float(entry[previous]["open"])) > 0
                        compressed = entry_atr[previous - 1] < entry_long_atr[previous - 1]
                        touched = compressed and directional \
                            and entry_true_ranges[previous] >= ec.volatility_expansion_ratio * entry_long_atr[previous]
                    else:
                        touched = False
                elif ec.entry_model == ElliottEntryModel.VOLUME_EXPANSION:
                    previous = candle_index - 1
                    if previous >= ec.volume_sma_period and previous_after_signal:
                        signal = entry[previous]
                        candle_range = float(signal["high"]) - float(signal["low"])
                        body = candidate_side * (float(signal["close"]) - float(signal["open"]))
                        expanded = float(signal.get("volume", 0)) \
                            >= ec.volume_expansion_ratio * entry_volume_average[previous - 1]
                        candidate_entry = (float(signal["high"]) + config.tick_size if candidate_side == 1
                                           else float(signal["low"]) - config.tick_size)
                        candidate_entry = round(candidate_entry / config.tick_size) * config.tick_size
                        touched = body > 0 and body / max(candle_range, 1e-12) > ec.volume_expansion_min_body_ratio \
                            and expanded and (high >= candidate_entry if candidate_side == 1 else low <= candidate_entry)
                    else:
                        touched = False
                if not touched:
                    continue
                processed.add(candidate.id)
                stop = candidate.points["P2"].price - candidate_side * ec.stop_buffer_atr * candidate.points["P2"].atr
                entry_price, stop, _ = _round_trade_prices(
                    candidate_entry, stop, [], candidate.direction, config.tick_size,
                )
                risk = abs(entry_price - stop)
                targets = [_fixed_rr_target(entry_price, stop, candidate.direction, ec.take_profit_rr)]
                if ec.take_profit_count == 2:
                    targets.append(_fixed_rr_target(
                        entry_price, stop, candidate.direction, ec.second_take_profit_rr,
                    ))
                _, _, targets = _round_trade_prices(
                    entry_price, stop, targets, candidate.direction, config.tick_size,
                )
                # Validate the RR of the executable, tick-rounded first target,
                # not an unused Elliott extension projection.
                rr = candidate_side * (targets[0] - entry_price) / max(risk, 1e-12)
                allowed = config.direction_mode == DirectionMode.BOTH or config.direction_mode.value == candidate.direction
                # A structural stop must always be on the loss side of the entry.
                # Reject malformed CHOCH retraces instead of producing a favorable
                # price move labelled as a stop loss.
                stop_on_loss_side = stop < entry_price if candidate_side == 1 else stop > entry_price
                if risk > 0 and rr >= ec.minimum_rr and allowed and stop_on_loss_side:
                    selected = candidate, entry_price, candidate_fee, stop, risk, targets
                    break
            if selected:
                pattern, entry_price, entry_fee_rate, stop, risk, targets = selected
                quantity = _elliott_position_quantity(
                    capital, config.initial_capital, entry_price, stop,
                    config.risk_per_trade_percent, config.position_size_percent,
                    ec.use_margin, config.leverage, ec.reinvest_profits, config.lot_size,
                )
                risk_capital = risk * quantity
                if quantity > 0:
                    traded.add(pattern.id)
                    position = {"pattern_id": pattern.id, "direction": pattern.direction, "entry_time": timestamp,
                                "entry_price": entry_price, "quantity": quantity, "stop": stop, "initial_stop": stop,
                                "targets": targets, "take_profit_prices": list(targets), "risk_capital": risk_capital,
                                "target_allocations": ([1.0] if ec.take_profit_count == 1
                                                       else list(ec.take_profit_allocations)),
                                "remaining": quantity, "realized": 0.0, "fees": 0.0, "funding": 0.0, "exits": [],
                                "break_even_active": False,
                                "entry_fee_rate": entry_fee_rate,
                                "last_funding_time": timestamp,
                                "signal_timeframe": ec.entry_timeframe,
                                "structure_timeframe": ec.structure_timeframe}
        # Market entries occur at the candle open; retracement entries occur
        # inside this candle. Without lower-timeframe ordering, apply the
        # conservative stop-first rule to the entry candle as well.
        if position and not had_position:
            side = 1 if position["direction"] == "LONG" else -1
            liquidation = _liquidation_price(position, config, taker_fee)
            margin_active = ec.use_margin and config.leverage > 1
            terminal = (max(position["stop"], liquidation) if side == 1 else min(position["stop"], liquidation)) \
                if margin_active else position["stop"]
            terminal_hit = low <= terminal if side == 1 else high >= terminal
            if terminal_hit:
                reason = "LIQUIDATION" if margin_active and terminal == liquidation else "STRUCTURAL_STOP"
                raw_terminal = min(float(candle["open"]), terminal) if side == 1 else max(float(candle["open"]), terminal)
                finish(raw_terminal, timestamp, reason)
            else:
                reached = ([target for target in position["targets"] if high >= target] if side == 1
                           else [target for target in position["targets"] if low <= target])
                for target in reached:
                    target_index = position["targets"].index(target)
                    position["targets"].pop(target_index)
                    allocation = position["target_allocations"].pop(target_index)
                    is_final = not position["targets"]
                    if is_final or ec.first_take_action.value == "PARTIAL_CLOSE":
                        finish(target, timestamp, "FIXED_RR_TARGET",
                               position["remaining"] if is_final else position["quantity"] * allocation)
                    if position and not is_final and ec.first_take_action.value == "MOVE_TO_BREAK_EVEN":
                        position["stop"] = _fee_adjusted_break_even_stop(
                            position["entry_price"], position["direction"], position["entry_fee_rate"],
                            taker_fee, slip, config.tick_size,
                        )
                        position["break_even_active"] = True
                activate_one_r_break_even(high, low)
        unrealized = 0 if not position else (
            (close - position["entry_price"]) * position["remaining"]
            * (1 if position["direction"] == "LONG" else -1)
            - position["entry_price"] * position["remaining"] * position["entry_fee_rate"]
        )
        equity.append({"timestamp": timestamp, "equity": capital + unrealized})
        if position:
            side = 1 if position["direction"] == "LONG" else -1
            adverse = low if side == 1 else high
            adverse_equity = capital + (adverse - position["entry_price"]) * position["remaining"] * side \
                - position["entry_price"] * position["remaining"] * position["entry_fee_rate"]
            equity[-1]["intrabar_min_equity"] = min(capital + unrealized, adverse_equity)
    if position:
        end_time = int(entry[-1]["timestamp"]) + TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        finish(float(entry[-1]["close"]), end_time, "END_OF_DATA")
        # Include the actual final fill, fees and slippage in risk metrics.
        equity.append({"timestamp": end_time, "equity": capital})
    evaluation_entry = [item for item in entry
                        if evaluation_start is None or int(item["timestamp"]) >= evaluation_start]
    peak, drawdown = config.initial_capital, 0.0
    for item in equity:
        peak = max(peak, item["equity"])
        observed_equity = item.get("intrabar_min_equity", item["equity"])
        drawdown = max(drawdown, (peak - observed_equity) / peak * 100)
    wins = [item for item in trades if item["pnl"] > 0]
    gross_profit = sum(item["pnl"] for item in wins)
    gross_loss = abs(sum(item["pnl"] for item in trades if item["pnl"] < 0))
    returns = [equity[i]["equity"] / equity[i - 1]["equity"] - 1 for i in range(1, len(equity)) if equity[i - 1]["equity"] > 0]
    periods_per_year = 365.25 * 86_400_000 / TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
    serialized = [{"id": item.id, "direction": item.direction, "state": item.state,
                   "invalid_reason": item.invalid_reason, "signal_time": item.signal_time,
                   "points": {key: _point(value) for key, value in item.points.items()}, "features": item.features,
                   "structure_timeframe": ec.structure_timeframe, "entry_timeframe": ec.entry_timeframe}
                  for item in patterns]
    counts: dict[str, int] = {}
    for item in patterns:
        counts[item.state] = counts.get(item.state, 0) + 1
    return {"initial_capital": config.initial_capital, "final_capital": capital,
            "net_profit": capital - config.initial_capital,
            "total_return_percent": (capital / config.initial_capital - 1) * 100,
            "max_drawdown_percent": drawdown, "win_rate": len(wins) / len(trades) * 100 if trades else 0,
            "profit_factor": gross_profit / gross_loss if gross_loss else None, "total_trades": len(trades),
            "average_trade": (capital - config.initial_capital) / len(trades) if trades else 0,
            "sharpe_ratio": mean(returns) / pstdev(returns) * sqrt(periods_per_year) if len(returns) > 1 and pstdev(returns) else 0,
            "benchmark_return_percent": ((float(evaluation_entry[-1]["close"])
                                           / float(evaluation_entry[0]["close"]) - 1) * 100
                                          if evaluation_entry else 0),
            "trades": trades, "equity": equity,
            **extended_performance(config.initial_capital, capital, equity),
            "chart_candles": entry[-50000:],
            "chart_candles_by_timeframe": {key: sorted(value, key=lambda item: item["timestamp"])[-50000:] for key, value in candles_by_tf.items()},
            "elliott_patterns": serialized,
            "elliott_swings_by_timeframe": {ec.structure_timeframe: [_point(item) for item in structure_pivots],
                                              ec.entry_timeframe: [_point(item) for item in entry_pivots]},
            "elliott_diagnostics": {"states": counts, "patterns": len(patterns), "signals": len(signals),
                                     "traded_signals": len(traded), "expired_signals": expired_signals,
                                     "lookahead_safe": True,
                                     "pivot_algorithm": "CAUSAL_NON_REPAINTING",
                                     "position_sizing": "STOP_RISK_CAPPED_BY_MARGIN",
                                     "risk_per_trade_percent": config.risk_per_trade_percent,
                                     "drawdown_basis": "INTRABAR_ADVERSE_EXTREME",
                                     "target_basis": "FIXED_RR",
                                     "selection_bias_warning": "Use a later untouched validation period after optimization.",
                                     "availability_basis": "CANDLE_CLOSE",
                                     "pivot_confirmation_uses_close_time": True,
                                     "macro_filter_uses_closed_candles_only": True,
                                     "entry_uses_next_candle_open": True,
                                     "excluded_v1_patterns": ["DIAGONAL", "FLAT", "TRIANGLE", "DOUBLE_THREE", "TRIPLE_THREE"]},
            "dataset": {
                "candles_by_timeframe": {key: len(value) for key, value in candles_by_tf.items()},
                "test_candles": len(evaluation_entry),
                "test_from": int(evaluation_entry[0]["timestamp"]) if evaluation_entry else None,
                "test_to": int(evaluation_entry[-1]["timestamp"]) if evaluation_entry else None,
                "closed_candles_only": True,
            }}
