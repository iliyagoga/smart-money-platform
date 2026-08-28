"""Adapter for joshyattridge/smart-money-concepts.

The package is evaluated on candles available so far. Its batch API uses
forward candles to confirm swings and mitigation, so evaluating a complete
test set would introduce look-ahead bias.
"""
from __future__ import annotations

from math import isnan
from typing import Any

try:
    import pandas as pd
    from smartmoneyconcepts import smc
except ImportError:
    pd = None
    smc = None

from .models import Candle, Direction, SwingType


def available() -> bool:
    return smc is not None and pd is not None


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if isnan(result) else result


class SmartMoneyConceptsAdapter:
    """Convert the package's DataFrame results to our overlay format."""

    def __init__(self, swing_length: int = 5):
        if not available():
            raise RuntimeError("smartmoneyconcepts is not installed")
        self.swing_length = max(2, int(swing_length))

    def detect(self, candles: list[Candle]) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
        if len(candles) < max(3, self.swing_length * 2 + 1):
            return [], [], [], [], []
        frame = pd.DataFrame({
            "open": [x.open for x in candles], "high": [x.high for x in candles],
            "low": [x.low for x in candles], "close": [x.close for x in candles],
            "volume": [x.volume for x in candles],
        })
        swings = smc.swing_highs_lows(frame, swing_length=self.swing_length)
        bos = smc.bos_choch(frame, swings, close_break=True)
        fvg = smc.fvg(frame, join_consecutive=False)
        ob = smc.ob(frame, swings, close_mitigation=False)
        liquidity = smc.liquidity(frame, swings, range_percent=0.01)
        swing_rows: list[dict] = []
        for index, row in swings.iterrows():
            kind = _number(row.get("HighLow")); price = _number(row.get("Level"))
            if kind is None or price is None: continue
            confirmed = min(len(candles) - 1, index + self.swing_length)
            swing_rows.append({"id": f"smc:swing:{candles[index].timeframe}:{index}", "timestamp": candles[index].timestamp,
                "available_at": candles[confirmed].timestamp,
                "price": price, "type": SwingType.HIGH.value if int(kind) == 1 else SwingType.LOW.value})
        change_rows: list[dict] = []
        for index, row in bos.iterrows():
            bos_direction = _number(row.get("BOS")); choch_direction = _number(row.get("CHOCH"))
            direction = bos_direction if bos_direction is not None else choch_direction
            level = _number(row.get("Level"))
            if direction is None or level is None: continue
            broken_index = int(_number(row.get("BrokenIndex")) or index)
            broken_index = max(index, min(len(candles) - 1, broken_index))
            broken_type = SwingType.HIGH.value if direction == 1 else SwingType.LOW.value
            broken_swing = next((item for item in reversed(swing_rows)
                                 if item["type"] == broken_type and item["timestamp"] <= candles[index].timestamp), None)
            change_rows.append({"id": f"smc:bos:{candles[index].timeframe}:{index}", "timestamp": candles[index].timestamp,
                "available_at": candles[broken_index].timestamp,
                "price": level, "type": "BOS" if bos_direction is not None else "CHOCH",
                "direction": Direction.BULLISH.value if direction == 1 else Direction.BEARISH.value,
                "broken_index": broken_index, "broken_swing_id": broken_swing["id"] if broken_swing else None})
        def zones(result, column: str, prefix: str) -> list[dict]:
            rows = []
            for index, row in result.iterrows():
                direction = _number(row.get(column)); high = _number(row.get("Top")); low = _number(row.get("Bottom"))
                if direction is None or high is None or low is None: continue
                mitigated = int(_number(row.get("MitigatedIndex")) or 0)
                available_index = min(len(candles) - 1, index + (1 if prefix == "fvg" else self.swing_length))
                end_at = candles[mitigated].timestamp if mitigated > available_index and mitigated < len(candles) else None
                source_break = next((change for change in change_rows
                    if change["direction"] == (Direction.BULLISH.value if direction == 1 else Direction.BEARISH.value)
                    and change["broken_index"] >= index), None)
                average_range = sum(c.high-c.low for c in candles[max(0,index-14):index+1]) / min(index+1, 15)
                displacement = abs(candles[min(len(candles)-1, available_index)].close-candles[index].close) / max(average_range, 1e-12)
                rows.append({"id": f"smc:{prefix}:{candles[index].timeframe}:{index}", "timestamp": candles[index].timestamp,
                    "available_at": candles[available_index].timestamp,
                    "low": min(low, high), "high": max(low, high),
                    "direction": Direction.BULLISH.value if direction == 1 else Direction.BEARISH.value,
                    "end_at": end_at, "size_atr": abs(high-low) / max(average_range, 1e-12),
                    "displacement_atr": displacement,
                    "body_low": min(candles[index].open, candles[index].close),
                    "body_high": max(candles[index].open, candles[index].close),
                    "ce": (low + high) / 2, "strength": (_number(row.get("Percentage")) or 0) / 100,
                    "source_break_id": source_break["id"] if source_break else None})
            return rows
        liquidity_rows = []
        for index, row in liquidity.iterrows():
            direction = _number(row.get("Liquidity")); level = _number(row.get("Level"))
            if direction is None or level is None: continue
            swept = int(_number(row.get("Swept")) or 0)
            liquidity_rows.append({"id": f"smc:liquidity:{candles[index].timeframe}:{index}",
                "timestamp": candles[index].timestamp, "price": level,
                "available_at": candles[min(len(candles)-1, index+self.swing_length)].timestamp,
                "type": "BUY_STOP" if direction == 1 else "SELL_STOP",
                "swept": swept > index and swept < len(candles),
                "swept_at": candles[swept].timestamp if swept > index and swept < len(candles) else None})
        return swing_rows, change_rows, zones(ob, "OB", "ob"), zones(fvg, "FVG", "fvg"), liquidity_rows
