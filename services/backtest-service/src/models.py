from enum import StrEnum
from pydantic import BaseModel, Field, model_validator


class StrategyType(StrEnum):
    SMC = "SMC"
    ELLIOTT = "ELLIOTT"
    SMA_CROSS = "SMA_CROSS"
    RSI = "RSI"
    MACD = "MACD"
    BOLLINGER = "BOLLINGER"


class DirectionMode(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


class ElliottEntryModel(StrEnum):
    CHOCH_MARKET = "CHOCH_MARKET"
    CHOCH_RETRACE = "CHOCH_RETRACE"
    WAVE1_BREAK_RETRACE = "WAVE1_BREAK_RETRACE"


class ElliottMacroFilter(StrEnum):
    OFF = "OFF"
    STRUCTURE = "STRUCTURE"
    EMA200 = "EMA200"
    EMA_CROSS = "EMA_CROSS"


class ElliottFirstTakeAction(StrEnum):
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    MOVE_TO_BREAK_EVEN = "MOVE_TO_BREAK_EVEN"


class ElliottConfig(BaseModel):
    use_margin: bool = False
    reinvest_profits: bool = True
    macro_timeframe: str = "H4"
    structure_timeframe: str = "H1"
    entry_timeframe: str = "M15"
    atr_period: int = Field(default=14, ge=2, le=200)
    zigzag_reversal_atr: float = Field(default=1.5, ge=.25, le=10)
    min_swing_atr: float = Field(default=1, ge=0, le=10)
    min_swing_candles: int = Field(default=2, ge=1, le=100)
    max_swing_candles: int | None = Field(default=80, ge=2, le=10000)
    wave1_min_atr: float = Field(default=1.5, ge=0, le=20)
    wave1_min_candles: int = Field(default=3, ge=1, le=1000)
    wave1_max_candles: int | None = Field(default=50, ge=2, le=10000)
    wave1_min_efficiency: float = Field(default=.45, ge=0, le=1)
    require_bos: bool = True
    bos_buffer_atr: float = Field(default=0, ge=0, le=5)
    wave2_min_retracement: float = Field(default=.382, ge=0, lt=1)
    wave2_max_retracement: float = Field(default=.786, gt=0, lt=1)
    wave2_min_time_ratio: float = Field(default=.2, ge=0, le=20)
    wave2_max_time_ratio: float = Field(default=3, gt=0, le=50)
    entry_model: ElliottEntryModel = ElliottEntryModel.CHOCH_RETRACE
    entry_retracement: float = Field(default=.5, ge=0, le=1)
    entry_expiry_bars: int = Field(default=4, ge=1, le=1000)
    choch_min_atr: float = Field(default=.5, ge=0, le=10)
    choch_min_body_ratio: float = Field(default=.5, ge=0, le=1)
    macro_filter: ElliottMacroFilter = ElliottMacroFilter.STRUCTURE
    adx_period: int = Field(default=14, ge=2, le=200)
    adx_min: float = Field(default=0, ge=0, le=100)
    require_di_confirmation: bool = False
    volume_sma_period: int = Field(default=20, ge=2, le=500)
    min_volume_ratio: float = Field(default=0, ge=0, le=100)
    stop_buffer_atr: float = Field(default=.2, ge=0, le=10)
    take_profit_extensions: list[float] = Field(default_factory=lambda: [1.0, 1.618])
    take_profit_allocations: list[float] = Field(default_factory=lambda: [.5, .5])
    take_profit_rr: float = Field(default=2, gt=0, le=100)
    take_profit_count: int = Field(default=2, ge=1, le=2)
    second_take_profit_rr: float = Field(default=3, gt=0, le=100)
    first_take_action: ElliottFirstTakeAction = ElliottFirstTakeAction.PARTIAL_CLOSE
    minimum_rr: float = Field(default=1.5, gt=0, le=100)
    break_even_at_one_r: bool = False
    mfe_mae_horizons: list[int] = Field(default_factory=lambda: [3, 6, 12, 24, 48, 96])

    @model_validator(mode="after")
    def validate_elliott(self):
        supported = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
        timeframes = (self.macro_timeframe, self.structure_timeframe, self.entry_timeframe)
        if any(item not in supported for item in timeframes):
            raise ValueError("unsupported Elliott timeframe")
        order = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
        if not order[self.entry_timeframe] < order[self.structure_timeframe] < order[self.macro_timeframe]:
            raise ValueError("Elliott timeframes must satisfy entry < structure < macro")
        if self.wave2_min_retracement >= self.wave2_max_retracement:
            raise ValueError("wave2 minimum retracement must be below maximum")
        if self.wave2_min_time_ratio >= self.wave2_max_time_ratio:
            raise ValueError("wave2 minimum time ratio must be below maximum")
        if not self.take_profit_extensions or any(value <= 0 for value in self.take_profit_extensions):
            raise ValueError("positive take-profit extensions are required")
        if len(self.take_profit_extensions) != len(self.take_profit_allocations):
            raise ValueError("take-profit extensions and allocations must have equal lengths")
        if abs(sum(self.take_profit_allocations) - 1) > 1e-6 or any(value <= 0 for value in self.take_profit_allocations):
            raise ValueError("take-profit allocations must be positive and sum to one")
        if self.take_profit_count == 2 and self.second_take_profit_rr <= self.take_profit_rr:
            raise ValueError("second take-profit RR must be greater than the first")
        return self


class BacktestConfig(BaseModel):
    strategy: StrategyType = StrategyType.SMC
    initial_capital: float = Field(default=10000, gt=0)
    position_size_percent: float = Field(default=25, gt=0, le=100)
    leverage: float = Field(default=1, ge=1, le=100)
    maintenance_margin_percent: float = Field(default=.5, ge=0, le=20)
    fee_percent: float = Field(default=.05, ge=0, le=10)
    maker_fee_percent: float | None = Field(default=None, ge=-1, le=10)
    taker_fee_percent: float | None = Field(default=None, ge=0, le=10)
    slippage_percent: float = Field(default=.02, ge=0, le=10)
    funding_percent_per_day: float = Field(default=0, ge=-10, le=10)
    funding_interval_hours: int = Field(default=8, ge=1, le=24)
    execution_latency_ms: int = Field(default=0, ge=0, le=86_400_000)
    tick_size: float = Field(default=.01, gt=0)
    lot_size: float = Field(default=.000001, gt=0)
    minimum_order_size: float = Field(default=.000001, gt=0)
    volume_participation_percent: float = Field(default=5, gt=0, le=100)
    liquidation_fee_percent: float = Field(default=.5, ge=0, le=10)
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
    smc_min_stop_percent: float = Field(default=.3, gt=0, le=10)
    smc_min_target_rr: float = Field(default=1.5, gt=0, le=100)
    smc_max_target_rr: float = Field(default=8, gt=0, le=1000)
    smc_target_rr: float | None = Field(default=None, gt=0, le=1000)
    kelly_fraction: float = Field(default=.25, ge=0, le=1)
    confidence_threshold: float = Field(default=.5, ge=0, le=1)
    template_ids: list[str] = Field(default_factory=list)
    local_retraining: bool = False
    elliott: ElliottConfig = Field(default_factory=ElliottConfig)

    @model_validator(mode="after")
    def validate_periods(self):
        if self.slow_period <= self.fast_period:
            raise ValueError("slow_period must be greater than fast_period")
        if self.rsi_oversold >= self.rsi_overbought:
            raise ValueError("rsi_oversold must be below rsi_overbought")
        if self.smc_min_target_rr >= self.smc_max_target_rr:
            raise ValueError("smc_min_target_rr must be below smc_max_target_rr")
        return self


class BacktestCreate(BaseModel):
    symbol: str
    timeframe: str = "M15"
    timeframes: list[str] = Field(default_factory=lambda: ["M5", "M15", "H1", "H4"])
    candle_limit: int = Field(default=10000, ge=100, le=2000000)
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
        supported = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}
        if not self.timeframes or self.timeframe not in supported or any(item not in supported for item in self.timeframes):
            raise ValueError("unsupported timeframe")
        if self.config.strategy == StrategyType.SMC:
            order = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
            self.timeframe = min(self.timeframes, key=order.__getitem__)
        elif self.config.strategy == StrategyType.ELLIOTT:
            required = [
                self.config.elliott.entry_timeframe,
                self.config.elliott.structure_timeframe,
                self.config.elliott.macro_timeframe,
            ]
            self.timeframes = list(dict.fromkeys([*self.timeframes, *required]))
            self.timeframe = self.config.elliott.entry_timeframe
        elif self.timeframe not in self.timeframes:
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
    tick_size: float | None = Field(default=None, gt=0)
    lot_size: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def normalize(self):
        self.symbol = self.symbol.strip().upper().replace("/", "-").replace("_", "-")
        self.category = self.category.strip().lower()
        return self
