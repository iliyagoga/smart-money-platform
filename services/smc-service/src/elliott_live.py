from __future__ import annotations

import re
from math import ceil, floor
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


@dataclass
class ElliottLiveEngine:
    emitted: set[str] = field(default_factory=set)
    wave1_broken: set[str] = field(default_factory=set)

    def generate(self, symbol: str, current: Candle, candles_by_tf: dict, raw_config: dict) -> list[Scenario]:
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
        patterns, _, _ = detect_patterns(series[ec.structure_timeframe], series[ec.entry_timeframe],
                                          series[ec.macro_timeframe], ec)
        available_at = current.timestamp + TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        expiry = ec.entry_expiry_bars * TIMEFRAME_MILLISECONDS[ec.entry_timeframe]
        result = []
        for pattern in sorted((item for item in patterns if item.signal_time), key=lambda item: item.signal_time):
            if pattern.id in self.emitted or available_at < pattern.signal_time or available_at > pattern.signal_time + expiry:
                continue
            side = 1 if pattern.direction == "LONG" else -1
            entry_model = str(ec.entry_model)
            entry_type = "MARKET" if entry_model == "CHOCH_MARKET" else "LIMIT"
            if entry_model == "CHOCH_RETRACE":
                level = pattern.features["choch_level"]
                signal_close = pattern.features["choch_close"]
                entry = level + side * ec.entry_retracement * abs(signal_close - level)
            elif entry_model == "WAVE1_BREAK_RETRACE":
                level = pattern.points["P1"].price
                broke = current.high > level if side == 1 else current.low < level
                if pattern.id not in self.wave1_broken:
                    if broke:
                        self.wave1_broken.add(pattern.id)
                    continue
                entry = level
            else:
                entry = current.close
            entry = round(entry / config.tick_size) * config.tick_size
            if entry_type == "LIMIT" and not current.low <= entry <= current.high:
                continue
            stop = pattern.points["P2"].price - side * ec.stop_buffer_atr * pattern.points["P2"].atr
            stop = (floor(stop / config.tick_size) if side == 1 else ceil(stop / config.tick_size)) * config.tick_size
            risk = abs(entry - stop)
            if risk <= 0 or (stop >= entry if side == 1 else stop <= entry):
                continue
            targets = [entry + side * risk * ec.take_profit_rr]
            if ec.take_profit_count == 2:
                targets.append(entry + side * risk * ec.second_take_profit_rr)
            targets = [
                (ceil(value / config.tick_size) if side == 1 else floor(value / config.tick_size)) * config.tick_size
                for value in targets
            ]
            allocations = [1.0] if ec.take_profit_count == 1 else list(ec.take_profit_allocations)
            first_take_action = str(ec.first_take_action)
            break_even = "ONE_R" if ec.break_even_at_one_r else (
                "AFTER_TARGET" if first_take_action == "MOVE_TO_BREAK_EVEN" else "OFF"
            )
            self.emitted.add(pattern.id)
            result.append(Scenario(
                id=pattern.id, symbol=symbol, timeframe=Timeframe(ec.entry_timeframe),
                direction=pattern.direction, setup_type="ELLIOTT_WAVE3", confidence=1,
                entry_zone_low=entry, entry_zone_high=entry, entry_type=entry_type,
                stop_loss_price=stop, take_profit_prices=targets, target_allocations=allocations,
                break_even_rule=break_even,
                move_stop_to_break_even_after_target=1 if break_even == "AFTER_TARGET" else None,
                one_trade_per_zone=True, deduplication_key=f"ELLIOTT:{pattern.id}",
                reasons=["Elliott Wave 2 confirmed", "Wave 3 CHOCH confirmed"],
                objects_used=[{"kind": "ELLIOTT_PATTERN", "id": pattern.id}],
                created_at=available_at, expires_at=pattern.signal_time + expiry,
            ))
        return result
