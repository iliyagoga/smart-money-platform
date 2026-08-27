from __future__ import annotations

from enum import StrEnum
from time import time
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator


class Timeframe(StrEnum): M1="M1"; M5="M5"; M15="M15"; M30="M30"; H1="H1"; H4="H4"; D1="D1"
class Direction(StrEnum): BULLISH="BULLISH"; BEARISH="BEARISH"
class TrendDirection(StrEnum): UP="UP"; DOWN="DOWN"; SIDEWAYS="SIDEWAYS"
class SwingType(StrEnum): HIGH="HIGH"; LOW="LOW"


class Candle(BaseModel):
    symbol: str; timeframe: Timeframe; timestamp: int = Field(ge=0)
    open: float = Field(gt=0); high: float = Field(gt=0); low: float = Field(gt=0); close: float = Field(gt=0)
    volume: float = Field(ge=0); quote_volume: float | None = None; trades_count: int | None = None; is_closed: bool = True
    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.low > self.high or not self.low <= self.open <= self.high or not self.low <= self.close <= self.high:
            raise ValueError("inconsistent OHLC")
        self.symbol = self.symbol.strip().upper()
        return self


class Swing(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; timestamp: int
    price: float; type: SwingType; strength: int = 1; lookback: int; is_confirmed: bool = True
    created_at: int = Field(default_factory=lambda:int(time()*1000)); prev_swing_id: str | None = None; next_swing_id: str | None = None


class Trend(BaseModel):
    symbol: str; timeframe: Timeframe; direction: TrendDirection; strength: float = Field(ge=0,le=1); timestamp: int


class StructureChange(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe
    type: str; direction: Direction; break_level_price: float; timestamp: int; confirmed: bool = True
    broken_swing_id: str | None = None; displacement_atr: float = 0


class OrderBlock(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; type: Direction
    zone_high: float; zone_low: float; strength_score: float = .5; retest_count: int = 0
    mitigation_depth: float = 0; is_active: bool = False; is_broken: bool = False; created_at: int
    source_break_id: str | None = None; source_candle_timestamp: int | None = None
    displacement_atr: float = 0; volume_ratio: float = 1; boundary_mode: str = "FULL"
    body_low: float | None = None; body_high: float | None = None
    traded: bool = False; last_touch_at: int | None = None; inside_zone: bool = False


class FVG(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; type: Direction
    zone_high: float; zone_low: float; is_filled: bool = False; fill_percent: float = 0; created_at: int
    consequent_encroachment: float | None = None; size_atr: float = 0; displacement_atr: float = 0


class LiquidityZone(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe
    type: str; price_level: float; swept: bool = False; swept_at: int | None = None
    strength: float = .5; created_at: int


class AnalysisResult(BaseModel):
    swings: list[Swing] = []; trend: Trend | None = None; changes: list[StructureChange] = []
    order_blocks: list[OrderBlock] = []; fvgs: list[FVG] = []; liquidity_zones: list[LiquidityZone] = []


class AlgorithmSignal(BaseModel):
    """Executable output of the built-in algorithm; it is not a generated scenario."""
    id: str = Field(default_factory=lambda:str(uuid4())); config_id: str; symbol: str; timeframe: Timeframe
    direction: str; entry_zone_low: float; entry_zone_high: float; stop_loss_price: float
    take_profit_prices: list[float]; score: float = Field(default=.5, ge=0, le=1)
    reason_codes: list[str] = []; object_ids: list[str] = []; zone_id: str | None = None
    one_trade_per_zone: bool = True; target_allocations: list[float] = []
    break_even_rule: str = "ONE_R"; move_stop_to_break_even_after_target: int | None = 1
    created_at: int; expires_at: int

    @property
    def setup_type(self): return self.config_id
    @property
    def confidence(self): return self.score
    @property
    def priority(self): return 50
    @property
    def reasons(self): return self.reason_codes
    @property
    def objects_used(self):
        return ([{"type":"ORDER_BLOCK","id":self.zone_id}] if self.zone_id else [])
