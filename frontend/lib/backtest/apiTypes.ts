import type { BacktestResult, BacktestTrade, EquityPoint } from "./types";

export interface BacktestRunSummary {
  id: string;
  symbol: string;
  timeframe: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  progress: number;
  error?: string;
  created_at: string;
  completed_at?: string;
}

export interface BacktestRun extends BacktestRunSummary {
  result?: BackendBacktestResult;
}

export interface BacktestRunsResponse { runs: BacktestRunSummary[] }
export interface BacktestCreateResponse { id: string; status: string }

interface BackendTrade {
  id: number;
  direction: "LONG" | "SHORT";
  entry_time: number;
  exit_time: number;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_percent: number;
  reason: BacktestTrade["reason"];
}

interface BackendEquityPoint { timestamp: number; equity: number }

export interface BackendBacktestResult {
  initial_capital: number;
  final_capital: number;
  net_profit: number;
  total_return_percent: number;
  max_drawdown_percent: number;
  win_rate: number;
  profit_factor?: number;
  total_trades: number;
  average_trade: number;
  sharpe_ratio: number;
  benchmark_return_percent: number;
  trades: BackendTrade[];
  equity: BackendEquityPoint[];
}

export function mapBacktestResult(result: BackendBacktestResult): BacktestResult {
  const trades: BacktestTrade[] = result.trades.map((trade) => ({
    id: trade.id,
    direction: trade.direction,
    entryTime: trade.entry_time,
    exitTime: trade.exit_time,
    entryPrice: trade.entry_price,
    exitPrice: trade.exit_price,
    quantity: trade.quantity,
    pnl: trade.pnl,
    pnlPercent: trade.pnl_percent,
    reason: trade.reason,
  }));
  const equity: EquityPoint[] = result.equity;
  return {
    initialCapital: result.initial_capital,
    finalCapital: result.final_capital,
    netProfit: result.net_profit,
    totalReturnPercent: result.total_return_percent,
    maxDrawdownPercent: result.max_drawdown_percent,
    winRate: result.win_rate,
    profitFactor: result.profit_factor,
    totalTrades: result.total_trades,
    averageTrade: result.average_trade,
    sharpeRatio: result.sharpe_ratio,
    benchmarkReturnPercent: result.benchmark_return_percent,
    trades,
    equity,
  };
}
