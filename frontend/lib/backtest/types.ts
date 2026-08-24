import type { Candle } from "../types";

export type TradeDirection = "LONG" | "SHORT";
export type DirectionMode = "LONG" | "SHORT" | "BOTH";
export type StrategyType = "SMC" | "SMA_CROSS" | "RSI" | "MACD" | "BOLLINGER";

export interface BacktestSettings {
  initialCapital: number;
  strategy: StrategyType;
  fastPeriod: number;
  slowPeriod: number;
  feePercent: number;
  makerFeePercent?: number;
  takerFeePercent?: number;
  slippagePercent: number;
  stopLossPercent: number;
  takeProfitPercent: number;
  positionSizePercent: number;
  leverage: number;
  maintenanceMarginPercent: number;
  fundingPercentPerDay: number;
  fundingIntervalHours?: number;
  executionLatencyMs?: number;
  tickSize?: number;
  lotSize?: number;
  minimumOrderSize?: number;
  volumeParticipationPercent?: number;
  liquidationFeePercent?: number;
  trailingStopPercent?: number;
  directionMode: DirectionMode;
  riskPerTradePercent: number;
  kellyFraction: number;
  confidenceThreshold: number;
  templateIds: string[];
  localRetraining: boolean;
}

export interface BacktestTrade {
  id: number;
  direction: TradeDirection;
  entryTime: number;
  exitTime: number;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
  pnlPercent: number;
  reason: "SIGNAL" | "STOP_LOSS" | "TAKE_PROFIT" | "LIQUIDATION" | "END_OF_DATA";
}

export interface EquityPoint { timestamp: number; equity: number }
export interface BacktestChartCandle { timestamp: number; open: number; high: number; low: number; close: number; volume: number }
export interface BacktestScenario {
  id: string; timestamp: number; expiresAt: number; timeframe: string; direction: TradeDirection;
  templateId: string; priority: number; confidence: number; entryZoneLow: number; entryZoneHigh: number;
  stopLossPrice: number; takeProfitPrices: number[]; reasons: string[]; decision: string;
}

export interface BacktestResult {
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
  trades: BacktestTrade[];
  equity: EquityPoint[];
  dataset?: {
    closedCandlesOnly: boolean;
    testCandles: number;
    testFrom?: number;
    testTo?: number;
    timeframes: string[];
  };
  modelTraining?: { mode: string; samples: number; version?: string };
  templateDistribution?: Record<string, { pnl: number; trades: number; wins: number }>;
  chartCandles: BacktestChartCandle[];
  chartCandlesByTimeframe: Record<string, BacktestChartCandle[]>;
  scenarios: BacktestScenario[];
  patternDiagnostics: Record<string, Record<string, number>>;
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
