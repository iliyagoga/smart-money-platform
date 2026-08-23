import type { Candle } from "../types";

export type TradeDirection = "LONG" | "SHORT";
export type DirectionMode = "LONG" | "SHORT" | "BOTH";

export interface BacktestSettings {
  initialCapital: number;
  fastPeriod: number;
  slowPeriod: number;
  feePercent: number;
  slippagePercent: number;
  stopLossPercent: number;
  takeProfitPercent: number;
  positionSizePercent: number;
  directionMode: DirectionMode;
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
  reason: "SIGNAL" | "STOP_LOSS" | "TAKE_PROFIT" | "END_OF_DATA";
}

export interface EquityPoint { timestamp: number; equity: number }

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
  trades: BacktestTrade[];
  equity: EquityPoint[];
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
