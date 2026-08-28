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
  scenario_id?: string;
  template_id?: string;
  initial_stop?: number;
  take_profit_prices?: number[];
  signal_timeframe?: string;
  structure_timeframe?: string;
  fees?: number;
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
  decisions?: Array<{
    confidence: number;
    decision: string;
    scenario_id: string;
    template_id: string;
    timestamp: number;
  }>;
  dataset?: {
    closed_candles_only: boolean;
    test_candles: number;
    test_from?: number;
    test_to?: number;
    timeframes: string[];
  };
  model_training?: { mode: string; samples: number; version?: string };
  template_distribution?: Record<string, { pnl: number; trades: number; wins: number }>;
  chart_candles?: Array<{ timestamp: number; open: number; high: number; low: number; close: number; volume: number }>;
  chart_candles_by_timeframe?: Record<string, Array<{
    timestamp: number; open: number; high: number; low: number; close: number; volume: number;
  }>>;
  scenarios?: Array<{
    id: string; timestamp: number; expires_at: number; timeframe: string; direction: "LONG" | "SHORT";
    template_id: string; priority: number; confidence: number; entry_zone_low: number; entry_zone_high: number;
    stop_loss_price: number; take_profit_prices: number[]; reasons: string[]; decision: string;
  }>;
  pattern_diagnostics?: Record<string, Record<string, number>>;
  elliott_patterns?: Array<{
    id: string; direction: "LONG" | "SHORT"; state: string; invalid_reason?: string; signal_time?: number;
    points: Record<string, { timestamp: number; confirmed_at: number; price: number; kind: "HIGH" | "LOW" }>;
    features: Record<string, number | string>; structure_timeframe: string; entry_timeframe: string;
  }>;
  elliott_diagnostics?: { states: Record<string, number>; patterns: number; signals: number; traded_signals: number; lookahead_safe: boolean };
  strategy_config?: {
    leverage: number;
    position_size_percent: number;
    stop_loss_percent?: number;
    take_profit_percent?: number;
  };
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
    scenarioId: trade.scenario_id,
    templateId: trade.template_id,
    initialStop: trade.initial_stop,
    takeProfitPrices: trade.take_profit_prices,
    signalTimeframe: trade.signal_timeframe,
    structureTimeframe: trade.structure_timeframe,
    fees: trade.fees,
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
    dataset: result.dataset ? {
      closedCandlesOnly: result.dataset.closed_candles_only,
      testCandles: result.dataset.test_candles,
      testFrom: result.dataset.test_from,
      testTo: result.dataset.test_to,
      timeframes: result.dataset.timeframes,
    } : undefined,
    modelTraining: result.model_training,
    templateDistribution: result.template_distribution,
    chartCandles: result.chart_candles ?? [],
    chartCandlesByTimeframe: result.chart_candles_by_timeframe ?? {},
    scenarios: (result.scenarios ?? []).map((item) => ({
      id: item.id, timestamp: item.timestamp, expiresAt: item.expires_at, timeframe: item.timeframe,
      direction: item.direction, templateId: item.template_id, priority: item.priority, confidence: item.confidence,
      entryZoneLow: item.entry_zone_low, entryZoneHigh: item.entry_zone_high,
      stopLossPrice: item.stop_loss_price, takeProfitPrices: item.take_profit_prices,
      reasons: item.reasons, decision: item.decision,
    })),
    patternDiagnostics: result.pattern_diagnostics ?? {},
    elliottPatterns: (result.elliott_patterns ?? []).map((item) => ({
      id: item.id, direction: item.direction, state: item.state, invalidReason: item.invalid_reason,
      signalTime: item.signal_time, features: item.features, structureTimeframe: item.structure_timeframe,
      entryTimeframe: item.entry_timeframe,
      points: Object.fromEntries(Object.entries(item.points).map(([key, point]) => [key, {
        timestamp: point.timestamp, confirmedAt: point.confirmed_at, price: point.price, kind: point.kind,
      }])),
    })),
    elliottDiagnostics: result.elliott_diagnostics ? {
      states: result.elliott_diagnostics.states, patterns: result.elliott_diagnostics.patterns,
      signals: result.elliott_diagnostics.signals, tradedSignals: result.elliott_diagnostics.traded_signals,
      lookaheadSafe: result.elliott_diagnostics.lookahead_safe,
    } : undefined,
    strategyConfig: result.strategy_config ? {
      leverage: result.strategy_config.leverage,
      positionSizePercent: result.strategy_config.position_size_percent,
      stopLossPercent: result.strategy_config.stop_loss_percent,
      takeProfitPercent: result.strategy_config.take_profit_percent,
    } : undefined,
  };
}
