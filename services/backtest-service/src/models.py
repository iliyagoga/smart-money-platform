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


class AlgorithmOverrides(BaseModel):
    entry_source: str = Field(default="ORDER_BLOCK", pattern="^(ORDER_BLOCK|FVG|OB_FVG)$")
    ob_entry_mode: str = Field(default="MIDPOINT", pattern="^(PROXIMAL|MIDPOINT)$")
    ob_boundary_mode: str = Field(default="FULL", pattern="^(FULL|BODY)$")
    require_fvg_overlap: bool = False
    require_liquidity_sweep_before_ob: bool = True
    require_ob_in_ote_zone: bool = True
    require_ob_caused_bos: bool = True
    minimum_ob_strength: float = Field(default=.45, ge=0, le=1)
    minimum_fvg_size_atr: float = Field(default=.1, ge=0, le=20)
    minimum_impulse_atr: float = Field(default=1, ge=0, le=20)
    volume_period: int = Field(default=20, ge=2, le=1000)
    minimum_volume_ratio: float = Field(default=.8, ge=0, le=100)
    adx_period: int = Field(default=14, ge=2, le=200)
    minimum_adx: float = Field(default=18, ge=0, le=100)
    stop_buffer_atr: float = Field(default=.1, ge=0, le=10)
    risk_reward: list[float] = Field(default_factory=lambda: [2], min_length=1, max_length=1)
    minimum_rr: float = Field(default=1.5, gt=0, le=100)
    entry_valid_for_bars: int = Field(default=30, ge=1, le=10000)
    one_trade_per_zone: bool = True
    break_even_rule: str = Field(default="ONE_R", pattern="^(ONE_R|AFTER_TARGET|NONE)$")
    target_allocations: list[float] = Field(default_factory=lambda: [1])

    @model_validator(mode="after")
    def validate_targets(self):
        if any(value < self.minimum_rr for value in self.risk_reward):
            raise ValueError("risk_reward values must satisfy minimum_rr")
        if (len(self.target_allocations) != len(self.risk_reward)
                or abs(sum(self.target_allocations) - 1) > 1e-6
                or any(value <= 0 for value in self.target_allocations)):
            raise ValueError("target allocations must match targets, be positive, and sum to one")
        return self


class OptimizationConfig(BaseModel):
    enabled: bool = False
    max_combinations: int = Field(default=64, ge=1, le=256)
    validation_candidates: int = Field(default=5, ge=1, le=20)
    minimum_trades: int = Field(default=5, ge=0, le=10000)
    drawdown_penalty: float = Field(default=1, ge=0, le=10)
    parameter_grid: dict[str, list[float | int | bool | str]] = Field(default_factory=dict)
    parameter_bounds: dict[str, list[float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_grid(self):
        allowed = {
            "minimum_ob_strength", "minimum_fvg_size_atr", "minimum_impulse_atr",
            "volume_period", "minimum_volume_ratio", "adx_period", "minimum_adx",
            "stop_buffer_atr", "minimum_rr", "entry_valid_for_bars",
            "require_fvg_overlap", "one_trade_per_zone",
        }
        unknown = (set(self.parameter_grid) | set(self.parameter_bounds)) - allowed
        if unknown:
            raise ValueError(f"unsupported optimization parameters: {', '.join(sorted(unknown))}")
        if any(not values for values in self.parameter_grid.values()):
            raise ValueError("optimization parameter values cannot be empty")
        if any(len(bounds) != 2 or bounds[0] > bounds[1] for bounds in self.parameter_bounds.values()):
            raise ValueError("optimization bounds must contain [minimum, maximum]")
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
    template_ids: list[str] = Field(default_factory=list)
    algorithm_overrides: dict[str, AlgorithmOverrides] = Field(default_factory=dict)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)

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
