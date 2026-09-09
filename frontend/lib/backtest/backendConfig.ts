import type { BacktestSettings } from "./types";

interface ExecutionOverrides {
  tickSize?: number;
  lotSize?: number;
  minimumOrderSize?: number;
}

export function toBackendBacktestConfig(
  value: BacktestSettings,
  overrides: ExecutionOverrides = {},
  preserved: Record<string, unknown> = {},
) {
  const e = value.elliott;
  const preservedElliott = preserved.elliott && typeof preserved.elliott === "object"
    ? preserved.elliott as Record<string, unknown>
    : {};
  return {
    ...preserved,
    strategy: value.strategy,
    initial_capital: value.initialCapital,
    position_size_percent: value.positionSizePercent,
    leverage: value.leverage,
    fee_percent: value.feePercent,
    maker_fee_percent: value.makerFeePercent,
    taker_fee_percent: value.takerFeePercent,
    slippage_percent: value.slippagePercent,
    funding_percent_per_day: value.fundingPercentPerDay,
    funding_interval_hours: value.fundingIntervalHours,
    execution_latency_ms: value.executionLatencyMs,
    tick_size: overrides.tickSize ?? value.tickSize,
    lot_size: overrides.lotSize ?? value.lotSize,
    minimum_order_size: overrides.minimumOrderSize ?? value.minimumOrderSize,
    volume_participation_percent: value.volumeParticipationPercent,
    liquidation_fee_percent: value.liquidationFeePercent,
    direction_mode: value.directionMode,
    risk_per_trade_percent: value.riskPerTradePercent,
    elliott: {
      ...preservedElliott,
      use_margin: e.useMargin,
      reinvest_profits: e.reinvestProfits,
      macro_timeframe: e.macroTimeframe,
      structure_timeframe: e.structureTimeframe,
      entry_timeframe: e.entryTimeframe,
      atr_period: e.atrPeriod,
      zigzag_reversal_atr: e.zigzagReversalAtr,
      min_swing_atr: e.minSwingAtr,
      wave1_min_atr: e.wave1MinAtr,
      wave1_min_efficiency: e.wave1MinEfficiency,
      wave2_min_retracement: e.wave2MinRetracement,
      wave2_max_retracement: e.wave2MaxRetracement,
      entry_model: e.entryModel,
      entry_retracement: e.entryRetracement,
      entry_expiry_bars: e.entryExpiryBars,
      breakout_buffer_atr: e.breakoutBufferAtr,
      retest_zone_atr: e.retestZoneAtr,
      displacement_min_atr: e.displacementMinAtr,
      displacement_min_body_ratio: e.displacementMinBodyRatio,
      displacement_retracement: e.displacementRetracement,
      sweep_min_wick_ratio: e.sweepMinWickRatio,
      volatility_expansion_ratio: e.volatilityExpansionRatio,
      volume_expansion_ratio: e.volumeExpansionRatio,
      volume_expansion_min_body_ratio: e.volumeExpansionMinBodyRatio,
      choch_min_atr: e.chochMinAtr,
      choch_min_body_ratio: e.chochMinBodyRatio,
      macro_filter: e.macroFilter,
      adx_period: e.adxPeriod,
      adx_min: e.adxMin,
      require_di_confirmation: e.requireDiConfirmation,
      stop_buffer_atr: e.stopBufferAtr,
      take_profit_count: e.takeProfitCount,
      take_profit_rr: e.takeProfitRr,
      second_take_profit_rr: e.secondTakeProfitRr,
      first_take_action: e.firstTakeAction,
      minimum_rr: e.minimumRr,
      break_even_at_one_r: e.breakEvenAtOneR,
    },
  };
}
