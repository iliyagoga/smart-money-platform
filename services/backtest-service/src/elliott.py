from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from statistics import mean, pstdev
from uuid import uuid4

from .models import BacktestConfig, DirectionMode, ElliottEntryModel, ElliottMacroFilter


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


def atr_zigzag(candles: list[dict], config) -> list[Pivot]:
    """ATR ZigZag whose pivot timestamp is separate from its later confirmation time."""
    if len(candles) < 3:
        return []
    atrs = _rolling(_true_ranges(candles), config.atr_period)
    direction = 0
    high_index = low_index = 0
    pivots: list[Pivot] = []

    def append(index: int, confirmed: int, kind: str):
        price = float(candles[index]["high" if kind == "HIGH" else "low"])
        if pivots and (pivots[-1].kind == kind or index - pivots[-1].index < config.min_swing_candles):
            if pivots and pivots[-1].kind == kind:
                better = price > pivots[-1].price if kind == "HIGH" else price < pivots[-1].price
                if better:
                    pivots[-1] = Pivot(index, int(candles[index]["timestamp"]), int(candles[confirmed]["timestamp"]), price, kind, atrs[index])
            return
        if pivots:
            distance = abs(price - pivots[-1].price)
            if distance < config.min_swing_atr * max(atrs[index], 1e-12):
                return
            if config.max_swing_candles and index - pivots[-1].index > config.max_swing_candles:
                return
        pivots.append(Pivot(index, int(candles[index]["timestamp"]), int(candles[confirmed]["timestamp"]), price, kind, atrs[index]))

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


def _macro_direction(candles: list[dict], timestamp: int, mode: ElliottMacroFilter) -> str:
    available = [item for item in candles if int(item["timestamp"]) <= timestamp]
    if mode == ElliottMacroFilter.OFF or len(available) < 3:
        return "BOTH"
    closes = [float(item["close"]) for item in available]
    if mode == ElliottMacroFilter.EMA200:
        return "LONG" if closes[-1] >= _ema(closes, 200)[-1] else "SHORT"
    if mode == ElliottMacroFilter.EMA_CROSS:
        return "LONG" if _ema(closes, 50)[-1] >= _ema(closes, 200)[-1] else "SHORT"
    return "LONG" if closes[-1] >= closes[max(0, len(closes) - 3)] else "SHORT"


def detect_patterns(structure: list[dict], entry: list[dict], macro: list[dict], config) -> tuple[list[Pattern], list[Pivot], list[Pivot]]:
    pivots = atr_zigzag(structure, config)
    entry_pivots = atr_zigzag(entry, config)
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
        pattern = Pattern(str(uuid4()), direction, {"P0": p0, "P1": p1, "P2": p2}, "WAVE2_CONFIRMED", features)
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
        macro_side = _macro_direction(macro, p2.confirmed_at, config.macro_filter)
        features["macro_direction"] = macro_side
        if macro_side not in ("BOTH", direction):
            invalid = "MACRO_FILTER"
        if invalid:
            pattern.state, pattern.invalid_reason = "INVALID", invalid
            patterns.append(pattern)
            continue

        candidates = [(index, candle) for index, candle in enumerate(entry) if int(candle["timestamp"]) > p2.confirmed_at]
        trigger = None
        for index, candle in candidates:
            prior_swings = [pivot for pivot in entry_pivots if pivot.confirmed_at < int(candle["timestamp"]) and pivot.timestamp >= p1.timestamp]
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
            pattern.state, pattern.signal_time = "WAVE3_POTENTIAL", int(candle["timestamp"])
            pattern.features.update({"choch_level": level, "choch_displacement_atr": displacement,
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


def run_elliott_replay(candles_by_tf: dict[str, list[dict]], config: BacktestConfig) -> dict:
    ec = config.elliott
    structure = sorted(candles_by_tf[ec.structure_timeframe], key=lambda item: item["timestamp"])
    entry = sorted(candles_by_tf[ec.entry_timeframe], key=lambda item: item["timestamp"])
    macro = sorted(candles_by_tf[ec.macro_timeframe], key=lambda item: item["timestamp"])
    patterns, structure_pivots, entry_pivots = detect_patterns(structure, entry, macro, ec)
    signals = sorted([item for item in patterns if item.signal_time], key=lambda item: item.signal_time)
    fee, slip = config.fee_percent / 100, config.slippage_percent / 100
    capital, trades, equity = config.initial_capital, [], []
    used: set[str] = set()
    position = None

    def finish(raw_price: float, timestamp: int, reason: str):
        nonlocal capital, position
        side = 1 if position["direction"] == "LONG" else -1
        exit_price = raw_price * (1 - slip * side)
        gross = (exit_price - position["entry_price"]) * position["quantity"] * side
        fees = (position["entry_price"] + exit_price) * position["quantity"] * fee
        pnl = gross - fees
        capital += pnl
        trades.append({**position, "id": len(trades) + 1, "exit_time": timestamp, "exit_price": exit_price,
                       "pnl": pnl, "pnl_percent": pnl / max(position["risk_capital"], 1e-12) * 100,
                       "fees": fees, "funding": 0, "reason": reason})
        for key in ("stop", "targets", "risk_capital", "remaining"):
            trades[-1].pop(key, None)
        position = None

    for candle in entry:
        timestamp = int(candle["timestamp"])
        high, low, close = float(candle["high"]), float(candle["low"]), float(candle["close"])
        if position:
            side = 1 if position["direction"] == "LONG" else -1
            stopped = low <= position["stop"] if side == 1 else high >= position["stop"]
            target = position["targets"][-1]
            hit = high >= target if side == 1 else low <= target
            if stopped:
                reason = "BREAK_EVEN" if position["stop"] == position["entry_price"] else "STRUCTURAL_STOP"
                finish(position["stop"], timestamp, reason)
            elif hit:
                finish(target, timestamp, "ELLIOTT_EXTENSION")
        if position is None:
            eligible = [item for item in signals if item.id not in used and item.signal_time <= timestamp]
            if eligible:
                pattern = eligible[0]
                used.add(pattern.id)
                side = 1 if pattern.direction == "LONG" else -1
                entry_price = close * (1 + slip * side)
                if ec.entry_model == ElliottEntryModel.CHOCH_RETRACE:
                    entry_price = pattern.features["choch_level"] + side * ec.entry_retracement * abs(close - pattern.features["choch_level"])
                stop = pattern.points["P2"].price - side * ec.stop_buffer_atr * pattern.points["P2"].atr
                risk = abs(entry_price - stop)
                wave1 = abs(pattern.points["P1"].price - pattern.points["P0"].price)
                targets = [pattern.points["P2"].price + side * extension * wave1 for extension in ec.take_profit_extensions]
                rr = side * (targets[0] - entry_price) / max(risk, 1e-12)
                allowed = config.direction_mode == DirectionMode.BOTH or config.direction_mode.value == pattern.direction
                # A structural stop must always be on the loss side of the entry.
                # Reject malformed CHOCH retraces instead of producing a favorable
                # price move labelled as a stop loss.
                stop_on_loss_side = stop < entry_price if side == 1 else stop > entry_price
                if risk > 0 and rr >= ec.minimum_rr and allowed and stop_on_loss_side:
                    risk_capital = capital * config.risk_per_trade_percent / 100
                    quantity = min(risk_capital / risk, capital * config.position_size_percent / 100 * config.leverage / entry_price)
                    if quantity >= config.minimum_order_size:
                        position = {"pattern_id": pattern.id, "direction": pattern.direction, "entry_time": timestamp,
                                    "entry_price": entry_price, "quantity": quantity, "stop": stop, "initial_stop": stop,
                                    "targets": targets, "take_profit_prices": targets, "risk_capital": risk_capital,
                                    "remaining": quantity, "signal_timeframe": ec.entry_timeframe,
                                    "structure_timeframe": ec.structure_timeframe}
        unrealized = 0 if not position else (close - position["entry_price"]) * position["quantity"] * (1 if position["direction"] == "LONG" else -1)
        equity.append({"timestamp": timestamp, "equity": capital + unrealized})
    if position:
        finish(float(entry[-1]["close"]), int(entry[-1]["timestamp"]), "END_OF_DATA")
    peak, drawdown = config.initial_capital, 0.0
    for item in equity:
        peak = max(peak, item["equity"])
        drawdown = max(drawdown, (peak - item["equity"]) / peak * 100)
    wins = [item for item in trades if item["pnl"] > 0]
    gross_profit = sum(item["pnl"] for item in wins)
    gross_loss = abs(sum(item["pnl"] for item in trades if item["pnl"] < 0))
    returns = [equity[i]["equity"] / equity[i - 1]["equity"] - 1 for i in range(1, len(equity)) if equity[i - 1]["equity"]]
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
            "sharpe_ratio": mean(returns) / pstdev(returns) * sqrt(252) if len(returns) > 1 and pstdev(returns) else 0,
            "benchmark_return_percent": (float(entry[-1]["close"]) / float(entry[0]["close"]) - 1) * 100,
            "trades": trades, "equity": equity, "decisions": [], "scenarios": [],
            "chart_candles": entry[-50000:],
            "chart_candles_by_timeframe": {key: sorted(value, key=lambda item: item["timestamp"])[-50000:] for key, value in candles_by_tf.items()},
            "elliott_patterns": serialized,
            "elliott_swings_by_timeframe": {ec.structure_timeframe: [_point(item) for item in structure_pivots],
                                              ec.entry_timeframe: [_point(item) for item in entry_pivots]},
            "elliott_diagnostics": {"states": counts, "patterns": len(patterns), "signals": len(signals),
                                     "traded_signals": len(used), "lookahead_safe": True,
                                     "excluded_v1_patterns": ["DIAGONAL", "FLAT", "TRIANGLE", "DOUBLE_THREE", "TRIPLE_THREE"]},
            "pattern_diagnostics": [], "template_distribution": {},
            "dataset": {
                "candles_by_timeframe": {key: len(value) for key, value in candles_by_tf.items()},
                "test_candles": len(entry),
                "test_from": int(entry[0]["timestamp"]) if entry else None,
                "test_to": int(entry[-1]["timestamp"]) if entry else None,
                "closed_candles_only": True,
            }}
