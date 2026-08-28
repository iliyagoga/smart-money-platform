import type { Candle } from "../types";

export type TradeDirection = "LONG" | "SHORT";
export type DirectionMode = "LONG" | "SHORT" | "BOTH";
export type StrategyType = "SMC" | "ELLIOTT" | "SMA_CROSS" | "RSI" | "MACD" | "BOLLINGER";

export interface ElliottSettings {
  useMargin: boolean;
  reinvestProfits: boolean;
  macroTimeframe: string; structureTimeframe: string; entryTimeframe: string;
  atrPeriod: number; zigzagReversalAtr: number; minSwingAtr: number;
  wave1MinAtr: number; wave1MinEfficiency: number;
  wave2MinRetracement: number; wave2MaxRetracement: number;
  entryModel: "CHOCH_MARKET" | "CHOCH_RETRACE" | "WAVE1_BREAK_RETRACE";
  entryRetracement: number; entryExpiryBars: number; chochMinAtr: number; chochMinBodyRatio: number;
  macroFilter: "OFF" | "STRUCTURE" | "EMA200" | "EMA_CROSS";
  stopBufferAtr: number; takeProfitCount: 1 | 2; takeProfitRr: number; secondTakeProfitRr: number;
  minimumRr: number; breakEvenAtOneR: boolean;
  firstTakeAction: "PARTIAL_CLOSE" | "MOVE_TO_BREAK_EVEN";
}

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
  smcTargetMode: "FIXED" | "TEMPLATE";
  smcTargetRr: number;
  smcMinTargetRr: number;
  smcMaxTargetRr: number;
  kellyFraction: number;
  confidenceThreshold: number;
  templateIds: string[];
  localRetraining: boolean;
  elliott: ElliottSettings;
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
  initialStop?: number;
  takeProfitPrices?: number[];
  exits?: Array<{ timestamp: number; price: number; quantity: number; pnl: number; fees: number; reason: string }>;
  signalTimeframe?: string;
  structureTimeframe?: string;
  fees?: number;
  reason: "SIGNAL" | "STOP_LOSS" | "TAKE_PROFIT" | "STRUCTURAL_STOP" | "ELLIOTT_EXTENSION"
    | "BREAK_EVEN" | "LIQUIDATION" | "END_OF_DATA";
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
  elliottPatterns: ElliottPattern[];
  elliottDiagnostics?: { states: Record<string, number>; patterns: number; signals: number; tradedSignals: number; lookaheadSafe: boolean };
  strategyConfig?: {
    leverage: number;
    positionSizePercent: number;
    useMargin?: boolean;
    reinvestProfits?: boolean;
    stopLossPercent?: number;
    takeProfitPercent?: number;
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
