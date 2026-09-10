import type { PortfolioResult } from "./apiTypes";

import type { Candle } from "../types";

export type TradeDirection = "LONG" | "SHORT";
export type DirectionMode = "LONG" | "SHORT" | "BOTH";
export type StrategyType = "ELLIOTT";

export interface ElliottSettings {
  useMargin: boolean;
  reinvestProfits: boolean;
  macroTimeframe: string; structureTimeframe: string; entryTimeframe: string;
  atrPeriod: number; zigzagReversalAtr: number; minSwingAtr: number;
  wave1MinAtr: number; wave1MinEfficiency: number;
  wave2MinRetracement: number; wave2MaxRetracement: number;
  entryModel: "CHOCH_MARKET" | "CHOCH_RETRACE" | "WAVE1_BREAK_RETRACE" | "WAVE1_BREAK_MARKET"
    | "WAVE1_BREAK_STOP" | "WAVE1_BREAK_RETEST_CONFIRM" | "MICRO_WAVE3" | "DISPLACEMENT_RETRACE"
    | "P2_LIQUIDITY_SWEEP" | "WAVE2_TRENDLINE_BREAK" | "ADX_ACCELERATION"
    | "VOLATILITY_EXPANSION" | "VOLUME_EXPANSION";
  entryRetracement: number; entryExpiryBars: number; chochMinAtr: number; chochMinBodyRatio: number;
  breakoutBufferAtr: number; retestZoneAtr: number; displacementMinAtr: number;
  displacementMinBodyRatio: number; displacementRetracement: number; sweepMinWickRatio: number;
  volatilityExpansionRatio: number; volumeExpansionRatio: number; volumeExpansionMinBodyRatio: number;
  macroFilter: "OFF" | "STRUCTURE" | "EMA200" | "EMA_CROSS";
  adxPeriod: number; adxMin: number; requireDiConfirmation: boolean;
  stopBufferAtr: number; takeProfitCount: 1 | 2; takeProfitRr: number; secondTakeProfitRr: number;
  minimumRr: number; breakEvenAtOneR: boolean;
  firstTakeAction: "PARTIAL_CLOSE" | "MOVE_TO_BREAK_EVEN";
}

export interface BacktestSettings {
  initialCapital: number;
  currentCapital?: number;
  strategy: StrategyType;
  feePercent: number;
  makerFeePercent?: number;
  takerFeePercent?: number;
  slippagePercent: number;
  positionSizePercent: number;
  leverage: number;
  fundingPercentPerDay: number;
  fundingIntervalHours?: number;
  executionLatencyMs?: number;
  tickSize?: number;
  lotSize?: number;
  minimumOrderSize?: number;
  volumeParticipationPercent?: number;
  liquidationFeePercent?: number;
  directionMode: DirectionMode;
  riskPerTradePercent: number;
  elliott: ElliottSettings;
}

export interface BacktestTrade {
  symbol?: string;
  leverage?: number;
  capitalBefore?: number;
  allocatedCapital?: number;
  allocationPercent?: number;
  id: number;
  direction: TradeDirection;
  entryTime: number;
  exitTime: number;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
  pnlPercent: number;
  scenarioId?: string;
  initialStop?: number;
  takeProfitPrices?: number[];
  exits?: Array<{ timestamp: number; price: number; quantity: number; pnl: number; fees: number; reason: string }>;
  signalTimeframe?: string;
  structureTimeframe?: string;
  fees?: number;
  reason: "SIGNAL" | "STOP_LOSS" | "TAKE_PROFIT" | "STRUCTURAL_STOP" | "ELLIOTT_EXTENSION" | "FIXED_RR_TARGET"
    | "BREAK_EVEN" | "LIQUIDATION" | "END_OF_DATA";
}

export interface EquityPoint { timestamp: number; equity: number }
export interface BacktestChartCandle { timestamp: number; open: number; high: number; low: number; close: number; volume: number }
export interface BacktestResult {
  portfolio?: PortfolioResult;
  initialCapital: number;
  finalCapital: number;
  netProfit: number;
  totalReturnPercent: number;
  maxDrawdownPercent: number;
  winRate: number;
  profitFactor?: number;
  totalTrades: number;
  averageTrade: number;
  sharpeRatio?: number;
  benchmarkReturnPercent?: number;
  averageMonthlyReturnPercent: number;
  annualizedReturnPercent: number;
  losingMonths: number;
  losingMonthsPercent: number;
  averageLosingMonthPercent: number;
  equityCurveRSquared: number;
  recoveryFactor?: number;
  trades: BacktestTrade[];
  equity: EquityPoint[];
  dataset?: {
    closedCandlesOnly: boolean;
    testCandles: number;
    testFrom?: number;
    testTo?: number;
    timeframes: string[];
  };
  chartCandles: BacktestChartCandle[];
  chartCandlesByTimeframe: Record<string, BacktestChartCandle[]>;
  elliottPatterns: ElliottPattern[];
  elliottDiagnostics?: {
    states: Record<string, number>; patterns: number; signals: number; tradedSignals: number; lookaheadSafe: boolean;
    strictChoch?: boolean; positionSizing?: string; riskPerTradePercent?: number; drawdownBasis?: string;
    targetBasis?: string; selectionBiasWarning?: string;
  };
  strategyConfig?: {
    leverage: number;
    positionSizePercent: number;
    useMargin?: boolean;
    reinvestProfits?: boolean;
  };
}

export interface ElliottPoint { timestamp: number; confirmedAt: number; price: number; kind: "HIGH" | "LOW" }
export interface ElliottPattern {
  id: string; direction: TradeDirection; state: string; invalidReason?: string; signalTime?: number;
  points: Record<string, ElliottPoint>; features: Record<string, number | string>;
  structureTimeframe: string; entryTimeframe: string;
}

export interface OpenBacktestPosition {
  direction: TradeDirection;
  entryPrice: number;
  entryTime: number;
  quantity: number;
}

export interface BacktestInput {
  candles: Candle[];
  settings: BacktestSettings;
}
