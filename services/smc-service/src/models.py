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


class OrderBlock(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; type: Direction
    zone_high: float; zone_low: float; strength_score: float = .5; retest_count: int = 0
    mitigation_depth: float = 0; is_active: bool = False; is_broken: bool = False; created_at: int


class FVG(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; type: Direction
    zone_high: float; zone_low: float; is_filled: bool = False; fill_percent: float = 0; created_at: int


class LiquidityZone(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe
    type: str; price_level: float; swept: bool = False; strength: float = .5; created_at: int


class AnalysisResult(BaseModel):
    swings: list[Swing] = []; trend: Trend | None = None; changes: list[StructureChange] = []
    order_blocks: list[OrderBlock] = []; fvgs: list[FVG] = []; liquidity_zones: list[LiquidityZone] = []


class Scenario(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; direction: str
    setup_type: str; priority: int = Field(default=50, ge=0, le=100)
    confidence: float = Field(ge=0,le=1); entry_zone_low: float; entry_zone_high: float
    stop_loss_price: float; take_profit_prices: list[float]; status: str = "ACTIVE"
    reasons: list[str] = []; objections: list[str] = []; objects_used: list[dict] = []
    created_at: int = Field(default_factory=lambda:int(time()*1000)); expires_at: int
