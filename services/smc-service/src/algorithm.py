from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, model_validator

from .engines import atr
from .models import AlgorithmSignal, Candle, Direction, SwingType, Timeframe, TrendDirection


TIMEFRAME_MILLISECONDS = {
    Timeframe.M1: 60_000, Timeframe.M5: 300_000, Timeframe.M15: 900_000,
    Timeframe.M30: 1_800_000, Timeframe.H1: 3_600_000,
    Timeframe.H4: 14_400_000, Timeframe.D1: 86_400_000,
}


class AlgorithmConfig(BaseModel):
    """Parameters for one fixed algorithm. The JSON cannot define executable logic."""
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    name: str
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    execution_timeframes: list[Timeframe] = [Timeframe.M1, Timeframe.M5, Timeframe.M15]
    allowed_directions: list[str] = ["LONG", "SHORT"]
    # Explicitly prevent signals against the detected trend.
    avoid_countertrend_entries: bool = True
    entry_source: str = "ORDER_BLOCK"
    ob_entry_mode: str = "MIDPOINT"
    ob_boundary_mode: str = "FULL"
    ob_mitigation_mode: str = "CLOSE_INSIDE"
    fvg_entry_mode: str = "FIFTY_PERCENT"
    require_fvg_overlap: bool = False
    require_liquidity_sweep_before_ob: bool = True
    require_ob_in_ote_zone: bool = True
    require_ob_caused_bos: bool = True
    minimum_ob_strength: float = Field(default=.45, ge=0, le=1)
    minimum_fvg_size_atr: float = Field(default=.1, ge=0, le=20)
    minimum_impulse_atr: float = Field(default=1, ge=0, le=20)
    volume_period: int = Field(default=20, ge=2, le=1000)
    minimum_volume_ratio: float = Field(default=0, ge=0, le=100)
    adx_period: int = Field(default=14, ge=2, le=200)
    minimum_adx: float = Field(default=0, ge=0, le=100)
    stop_buffer_atr: float = Field(default=.1, ge=0, le=10)
    risk_reward: list[float] = [2]
    minimum_rr: float = Field(default=1.5, gt=0, le=100)
    entry_valid_for_bars: int = Field(default=30, ge=1, le=10000)
    one_trade_per_zone: bool = True
    break_even_rule: str = "ONE_R"
    target_allocations: list[float] = [1]

    @model_validator(mode="after")
    def valid_modes(self):
        if self.entry_source not in {"ORDER_BLOCK", "FVG", "OB_FVG"}:
            raise ValueError("unsupported entry source")
        if self.ob_entry_mode not in {"PROXIMAL", "MIDPOINT"}:
            raise ValueError("unsupported OB entry mode")
        if self.ob_boundary_mode not in {"FULL", "BODY"}:
            raise ValueError("unsupported OB boundary mode")
        if self.ob_mitigation_mode not in {"TOUCH", "CLOSE_INSIDE", "FULL", "NEVER"}:
            raise ValueError("unsupported OB mitigation mode")
        if self.fvg_entry_mode != "FIFTY_PERCENT":
            raise ValueError("unsupported FVG entry mode")
        if len(self.risk_reward) != 1 or any(value < self.minimum_rr for value in self.risk_reward):
            raise ValueError("exactly one risk_reward value must satisfy minimum_rr")
        if self.target_allocations and (len(self.target_allocations) != len(self.risk_reward)
                or abs(sum(self.target_allocations) - 1) > 1e-6):
            raise ValueError("target allocations must match targets and sum to one")
        if not self.allowed_directions or any(value not in {"LONG", "SHORT"} for value in self.allowed_directions):
            raise ValueError("unsupported direction")
        return self


class AlgorithmConfigStore:
    def __init__(self, directory: str | Path | None = None):
        configured = directory or os.getenv("ALGORITHM_CONFIG_DIR", "/app/algorithm-configs")
        self.directory = Path(configured)

    def list(self) -> list[AlgorithmConfig]:
        if not self.directory.exists():
            return []
        return [AlgorithmConfig.model_validate_json(path.read_text(encoding="utf-8"))
                for path in sorted(self.directory.glob("*.json"))]

    def enabled(self, selected: set[str] | None = None) -> list[AlgorithmConfig]:
        return [item for item in self.list() if item.enabled and (not selected or item.id in selected)]

    def get(self, config_id: str) -> AlgorithmConfig | None:
        return next((item for item in self.list() if item.id == config_id.upper()), None)

    def save(self, config: AlgorithmConfig) -> AlgorithmConfig:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{config.id}.json").write_text(config.model_dump_json(indent=2), encoding="utf-8")
        return config


def adx(candles: list[Candle], period: int = 14) -> float:
    """Wilder-style ADX without third-party dependencies."""
    if candles and f"adx:{period}" in candles[-1].indicators:
        return candles[-1].indicators[f"adx:{period}"]
    if len(candles) < period * 2 + 1:
        if candles:
            candles[-1].indicators[f"adx:{period}"] = 0
        return 0
    trs, plus_dm, minus_dm = [], [], []
    for previous, current in zip(candles[:-1], candles[1:]):
        up = current.high - previous.high
        down = previous.low - current.low
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        trs.append(max(current.high-current.low, abs(current.high-previous.close), abs(current.low-previous.close)))
    dx = []
    for end in range(period, len(trs)+1):
        tr = sum(trs[end-period:end])
        if tr <= 0:
            dx.append(0); continue
        plus = 100 * sum(plus_dm[end-period:end]) / tr
        minus = 100 * sum(minus_dm[end-period:end]) / tr
        dx.append(100 * abs(plus-minus) / max(plus+minus, 1e-12))
    result = sum(dx[-period:]) / min(period, len(dx))
    candles[-1].indicators[f"adx:{period}"] = result
    return result


class AlgorithmEngine:
    """Fixed BOS → OB/FVG retest algorithm configured only by numeric/mode inputs."""
    def __init__(self, store: AlgorithmConfigStore | None = None):
        self.store = store or AlgorithmConfigStore()
        self.emitted: set[str] = set()
        self.diagnostics: dict[str, dict[str, int]] = {}

    def _reject(self, config_id: str, reason: str):
        bucket = self.diagnostics.setdefault(config_id, {})
        bucket[reason] = bucket.get(reason, 0) + 1

    def generate(self, candle: Candle, pipeline, selected: set[str] | None = None) -> list[AlgorithmSignal]:
        key = (candle.symbol, candle.timeframe)
        bars = pipeline.candles[key]
        result = []
        for config in self.store.enabled(selected):
            if candle.timeframe not in config.execution_timeframes:
                continue
            trend = pipeline.trends.get(key)
            if not trend or trend.direction == TrendDirection.SIDEWAYS:
                self._reject(config.id, "NO_TREND"); continue
            direction = "LONG" if trend.direction == TrendDirection.UP else "SHORT"
            if not config.avoid_countertrend_entries:
                # When explicitly disabled, permit the newest eligible POI to
                # define the side, including a counter-trend retest.
                newest = max((item for item in pipeline.obs[key] if not item.is_broken),
                             key=lambda item: item.created_at, default=None)
                if newest is not None:
                    direction = "LONG" if newest.type == Direction.BULLISH else "SHORT"
            side = Direction.BULLISH if direction == "LONG" else Direction.BEARISH
            if direction not in config.allowed_directions:
                continue
            if config.avoid_countertrend_entries and ((direction == "LONG" and trend.direction != TrendDirection.UP)
                                                      or (direction == "SHORT" and trend.direction != TrendDirection.DOWN)):
                self._reject(config.id, "COUNTERTREND_ENTRY_BLOCKED")
                continue
            blocks = [item for item in pipeline.obs[key] if item.type == side and not item.is_broken
                      and not (config.one_trade_per_zone and item.traded)
                      and item.strength_score >= config.minimum_ob_strength
                      and item.displacement_atr >= config.minimum_impulse_atr]
            if not blocks:
                self._reject(config.id, "NO_ACTIVE_OB"); continue
            block = max(blocks, key=lambda item: item.created_at)
            if config.require_ob_caused_bos:
                source_break = next((item for item in pipeline.changes[key]
                                     if item.id == block.source_break_id
                                     and (block.source_candle_timestamp is None or item.timestamp >= block.source_candle_timestamp)), None)
                if not source_break or not source_break.broken_swing_id or block.source_candle_timestamp is None:
                    self._reject(config.id, "OB_DID_NOT_CAUSE_BOS"); continue
            if config.require_liquidity_sweep_before_ob:
                required_pool = "SELL_STOP" if direction == "LONG" else "BUY_STOP"
                sweep_deadline = block.source_candle_timestamp or block.created_at
                sweep = next((item for item in reversed(pipeline.liquidity[key])
                              if item.type == required_pool and item.swept
                              and item.swept_at is not None and item.swept_at <= sweep_deadline), None)
                if not sweep:
                    self._reject(config.id, "NO_LIQUIDITY_SWEEP_BEFORE_OB"); continue
            if config.require_ob_in_ote_zone:
                structural = [item for item in pipeline.swings[key] if item.timestamp <= block.created_at]
                highs = [item.price for item in structural if item.type == SwingType.HIGH]
                lows = [item.price for item in structural if item.type == SwingType.LOW]
                if not highs or not lows:
                    self._reject(config.id, "NO_OTE_STRUCTURAL_LEG"); continue
                swing_high, swing_low = highs[-1], lows[-1]
                if swing_high <= swing_low:
                    self._reject(config.id, "NO_OTE_STRUCTURAL_LEG"); continue
                price_range = swing_high - swing_low
                ote_low, ote_high = ((swing_high - price_range * .786, swing_high - price_range * .618)
                                     if direction == "LONG" else
                                     (swing_low + price_range * .618, swing_low + price_range * .786))
                ob_midpoint = (block.zone_low + block.zone_high) / 2
                if not ote_low <= ob_midpoint <= ote_high:
                    self._reject(config.id, "OB_OUTSIDE_OTE_ZONE"); continue
            gaps = [item for item in pipeline.fvgs[key] if item.type == side and not item.is_filled
                    and item.size_atr >= config.minimum_fvg_size_atr]
            overlap = next((item for item in gaps if item.zone_low <= block.zone_high
                            and item.zone_high >= block.zone_low), None)
            if (config.require_fvg_overlap or config.entry_source == "OB_FVG") and not overlap:
                self._reject(config.id, "NO_OB_FVG_OVERLAP"); continue
            current_atr = atr(bars)
            recent = bars[-config.volume_period:]
            average_volume = sum(item.volume for item in recent) / max(len(recent), 1)
            volume_ratio = candle.volume / max(average_volume, 1e-12)
            if volume_ratio < config.minimum_volume_ratio:
                self._reject(config.id, "LOW_VOLUME"); continue
            current_adx = adx(bars, config.adx_period)
            if current_adx < config.minimum_adx:
                self._reject(config.id, "LOW_ADX"); continue
            selected_gap = overlap or (max(gaps,key=lambda item:item.created_at) if gaps else None)
            if config.entry_source == "FVG" and not selected_gap:
                self._reject(config.id,"NO_ACTIVE_FVG");continue
            block_low = block.body_low if config.ob_boundary_mode=="BODY" and block.body_low is not None else block.zone_low
            block_high = block.body_high if config.ob_boundary_mode=="BODY" and block.body_high is not None else block.zone_high
            if config.entry_source == "FVG" and selected_gap:
                low = high = (selected_gap.zone_low + selected_gap.zone_high) / 2
            elif config.entry_source == "OB_FVG" and overlap:
                low, high = max(block_low, overlap.zone_low), min(block_high, overlap.zone_high)
            elif config.ob_entry_mode == "MIDPOINT":
                low = high = (block_low + block_high) / 2
            else:
                low = high = block_high if direction == "LONG" else block_low
            touched = candle.low <= high and candle.high >= low
            if touched or candle.timestamp <= block.created_at:
                self._reject(config.id, "WAITING_RETEST"); continue
            # Emit a pending limit signal before the future retest; replay/live execution owns the fill.
            entry = (low + high) / 2
            stop = (block.zone_low - current_atr * config.stop_buffer_atr if direction == "LONG"
                    else block.zone_high + current_atr * config.stop_buffer_atr)
            risk = abs(entry-stop)
            if risk <= 0:
                self._reject(config.id, "INVALID_RISK"); continue
            targets = [entry + risk*ratio*(1 if direction == "LONG" else -1) for ratio in config.risk_reward]
            identity = f"{config.id}:{block.id}"
            if identity in self.emitted:
                continue
            self.emitted.add(identity)
            score = min(.99, .35 + .35*block.strength_score + .15*min(2, volume_ratio)/2
                        + .15*min(50, current_adx)/50)
            signal_id = str(uuid5(NAMESPACE_URL, identity))
            result.append(AlgorithmSignal(
                id=signal_id, config_id=config.id, symbol=candle.symbol, timeframe=candle.timeframe,
                direction=direction, entry_zone_low=low, entry_zone_high=high,
                stop_loss_price=stop, take_profit_prices=targets, score=score,
                reason_codes=["FIXED_BOS_OB_RETEST", "OB_CAUSED_BOS", "LIQUIDITY_SWEEP_BEFORE_OB",
                              "OB_IN_OTE_ZONE", f"ADX:{current_adx:.2f}", f"VOLUME_RATIO:{volume_ratio:.2f}"],
                object_ids=[block.id] + ([selected_gap.id] if selected_gap else []), zone_id=block.id,
                one_trade_per_zone=config.one_trade_per_zone,
                target_allocations=config.target_allocations,
                break_even_rule=config.break_even_rule,
                created_at=candle.timestamp,
                expires_at=candle.timestamp + config.entry_valid_for_bars*TIMEFRAME_MILLISECONDS[candle.timeframe],
            ))
        return result
