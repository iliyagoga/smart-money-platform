from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class StrategyType(StrEnum):
    SMC = "SMC"
    SMA_CROSS = "SMA_CROSS"
    RSI = "RSI"
    MACD = "MACD"
    BOLLINGER = "BOLLINGER"


class DirectionMode(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


class BacktestConfig(BaseModel):
    strategy: StrategyType = StrategyType.SMC
    initial_capital: float = Field(default=10000, gt=0)
    position_size_percent: float = Field(default=25, gt=0, le=100)
    leverage: float = Field(default=1, ge=1, le=100)
    maintenance_margin_percent: float = Field(default=.5, ge=0, le=20)
    fee_percent: float = Field(default=.05, ge=0, le=10)
    slippage_percent: float = Field(default=.02, ge=0, le=10)
    funding_percent_per_day: float = Field(default=0, ge=-10, le=10)
    stop_loss_percent: float = Field(default=2, gt=0, le=100)
    take_profit_percent: float = Field(default=4, gt=0, le=1000)
    trailing_stop_percent: float | None = Field(default=None, gt=0, le=100)
    fast_period: int = Field(default=9, ge=2, le=500)
    slow_period: int = Field(default=21, ge=3, le=1000)
    rsi_period: int = Field(default=14, ge=2, le=500)
    rsi_oversold: float = Field(default=30, ge=0, le=100)
    rsi_overbought: float = Field(default=70, ge=0, le=100)
    direction_mode: DirectionMode = DirectionMode.BOTH
    risk_per_trade_percent: float = Field(default=1, gt=0, le=10)
    kelly_fraction: float = Field(default=.25, ge=0, le=1)
    confidence_threshold: float = Field(default=.6, ge=0, le=1)
    template_ids: list[str] = Field(default_factory=list)
    local_retraining: bool = False

    @model_validator(mode="after")
    def validate_periods(self):
        if self.slow_period <= self.fast_period:
            raise ValueError("slow_period must be greater than fast_period")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("rsi_oversold must be below rsi_overbought")
        return self


class BacktestCreate(BaseModel):
    symbol: str
    timeframe: str = "M15"
    timeframes: list[str] = Field(default_factory=lambda: ["M5", "M15", "H1", "H4"])
    candle_limit: int = Field(default=1000, ge=100, le=10000)
    train_from: int | None = Field(default=None, ge=0)
    train_to: int | None = Field(default=None, ge=0)
    test_from: int | None = Field(default=None, ge=0)
    test_to: int | None = Field(default=None, ge=0)
    model_version: str | None = None
    config: BacktestConfig = Field(default_factory=BacktestConfig)

    @model_validator(mode="after")
    def normalize(self):
        self.symbol = self.symbol.strip().upper()
        self.timeframe = self.timeframe.strip().upper()
        self.timeframes = list(dict.fromkeys(item.strip().upper() for item in self.timeframes))
        supported = {"M1", "M5", "M15", "H1", "H4", "D1"}
        if self.timeframe not in supported or any(item not in supported for item in self.timeframes):
            raise ValueError("unsupported timeframe")
        if self.timeframe not in self.timeframes:
            self.timeframes.append(self.timeframe)
        values = (self.train_from, self.train_to, self.test_from, self.test_to)
        if any(value is not None for value in values):
            if any(value is None for value in values):
                raise ValueError("all train/test boundaries are required")
            if not self.train_from < self.train_to < self.test_from < self.test_to:
                raise ValueError("periods must satisfy train_from < train_to < test_from < test_to")
        return self


class AssetCreate(BaseModel):
    symbol: str
    display_name: str | None = None
    category: str = "crypto"
    price_precision: int = Field(default=2, ge=0, le=18)
    quantity_precision: int = Field(default=6, ge=0, le=18)
    minimum_order_size: float = Field(default=.000001, gt=0)

    @model_validator(mode="after")
    def normalize(self):
        self.symbol = self.symbol.strip().upper().replace("/", "-").replace("_", "-")
        self.category = self.category.strip().lower()
        return self
