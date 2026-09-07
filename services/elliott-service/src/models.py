from __future__ import annotations

from enum import StrEnum
from time import time
from uuid import uuid4
from pydantic import BaseModel, Field, model_validator


class Timeframe(StrEnum): M1="M1"; M5="M5"; M15="M15"; M30="M30"; H1="H1"; H4="H4"; D1="D1"


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


class Scenario(BaseModel):
    id: str = Field(default_factory=lambda:str(uuid4())); symbol: str; timeframe: Timeframe; direction: str
    setup_type: str; priority: int = Field(default=50, ge=0, le=100)
    confidence: float = Field(ge=0,le=1); entry_zone_low: float; entry_zone_high: float
    stop_loss_price: float; take_profit_prices: list[float]; status: str = "ACTIVE"
    reasons: list[str] = []; objections: list[str] = []; objects_used: list[dict] = []
    target_allocations: list[float] = []
    entry_type: str = "LIMIT"
    break_even_rule: str = "ONE_R"
    move_stop_to_break_even_after_target: int | None = 1
    one_trade_per_zone: bool = False; cooldown_bars_after_stop: int = 0
    deduplication_key: str | None = None
    created_at: int = Field(default_factory=lambda:int(time()*1000)); expires_at: int
