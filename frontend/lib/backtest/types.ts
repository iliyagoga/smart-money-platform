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
  autoOptimize: boolean;
  optimizationMaxCombinations: number;
  optimizationValidationCandidates: number;
  optimizationMinimumTrades: number;
  optimizationDrawdownPenalty: number;
  optimizationBounds: {
    minimumObStrength: { minimum?: number; maximum?: number };
    minimumImpulseAtr: { minimum?: number; maximum?: number };
    minimumVolumeRatio: { minimum?: number; maximum?: number };
    minimumAdx: { minimum?: number; maximum?: number };
    stopBufferAtr: { minimum?: number; maximum?: number };
  };
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
  scenarioId?: string;
  templateId?: string;
  reason: "SIGNAL" | "STOP_LOSS" | "TAKE_PROFIT" | "LIQUIDATION" | "END_OF_DATA";
}

export interface EquityPoint { timestamp: number; equity: number }
export interface BacktestChartCandle {
  timestamp: number; open: number; high: number; low: number; close: number; volume: number;
  indicators?: Record<string, number>;
}
export interface BacktestScenario {
  id: string; timestamp: number; expiresAt: number; timeframe: string; direction: TradeDirection;
  templateId: string; priority: number; confidence: number; entryZoneLow: number; entryZoneHigh: number;
  stopLossPrice: number; takeProfitPrices: number[]; reasons: string[]; decision: string;
}
export interface BacktestStructureOverlay {
  swings: Array<{ id: string; timestamp: number; price: number; type: "HIGH" | "LOW" }>;
  changes: Array<{ id: string; timestamp: number; price: number; type: string; direction: "BULLISH" | "BEARISH" }>;
  orderBlocks: Array<{ id: string; timestamp: number; low: number; high: number; direction: "BULLISH" | "BEARISH"; strength: number; endAt?: number; status: string }>;
  fvgs: Array<{ id: string; timestamp: number; low: number; high: number; ce?: number; direction: "BULLISH" | "BEARISH"; endAt?: number; status: string }>;
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
  structureOverlaysByTimeframe: Record<string, BacktestStructureOverlay>;
  scenarios: BacktestScenario[];
  patternDiagnostics: Record<string, Record<string, number>>;
  optimization?: {
    testedCombinations: number;
    validatedCandidates: number;
    objective: string;
    bestParameters: Record<string, number | boolean | string>;
    validationLeaderboard: Array<{
      parameters: Record<string, number | boolean | string>;
      score?: number;
      totalReturnPercent: number;
      maxDrawdownPercent: number;
      totalTrades: number;
      winRate: number;
    }>;
  };
  strategyConfig?: {
    leverage: number;
    positionSizePercent: number;
    stopLossPercent?: number;
    takeProfitPercent?: number;
  };
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
