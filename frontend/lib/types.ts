export interface Portfolio {
  total_equity: number;
  realized_pnl_today: number;
  unrealized_pnl: number;
  available_balance: number;
}

export interface Position {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry_price: number;
  current_price?: number;
  quantity: number;
  status: string;
}

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  symbol: string;
  timeframe: string;
  candles: Candle[];
}

export interface MarketStructure {
  last_swing_high?: number;
  last_swing_low?: number;
  trend?: { direction: string; strength: number };
  order_blocks: Array<{ id: string; zone_high: number; zone_low: number; type: string }>;
  fvgs: Array<{ id: string; zone_high: number; zone_low: number; type: string }>;
}

export interface ServiceStatus {
  name: string;
  status: "UP" | "DOWN" | string;
}

export interface PlatformEvent {
  event_type: string;
  timestamp: string;
  source?: string;
  payload?: { symbol?: string; timeframe?: string };
}

export interface ServicesResponse {
  services?: ServiceStatus[];
}

export interface PositionsResponse {
  positions?: Position[];
}

export interface OrderDraft {
  symbol: string;
  side: "BUY" | "SELL";
  type: "MARKET" | "LIMIT" | "STOP";
  price?: number;
  quantity: number;
  stop_loss_price?: number;
  take_profit_prices: number[];
}

export interface ClosedTrade {
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_percent?: number;
  initial_stop_loss_price?: number;
  r_multiple?: number;
  duration_seconds?: number;
  max_unrealized_pnl?: number;
  reason: string;
  closed_at: number;
}

export interface TradesResponse {
  trades: ClosedTrade[];
  total: number;
}

export interface TradeAssetsResponse {
  assets: Array<{ symbol: string; trades_count: number }>;
}

export interface TradeStatistics {
  total_trades: number;
  win_rate: number;
  profit_factor?: number;
  avg_profit: number;
  avg_loss: number;
  max_drawdown: number;
}

export interface TradeAnalysisMetrics {
  total_trades: number;
  net_pnl: number;
  win_rate: number;
  profit_factor?: number;
  expectancy: number;
  payoff_ratio?: number;
  average_r?: number;
  average_duration_seconds: number;
}

export interface EntryPointAnalysis {
  position_id: string;
  symbol: string;
  direction: string;
  entry_price: number;
  exit_price: number;
  initial_stop_loss_price?: number;
  pnl: number;
  pnl_percent: number;
  r_multiple?: number;
  capture_rate?: number;
  duration_seconds: number;
  reason: string;
  closed_at: number;
}

export interface TradeAnalysisResponse {
  metrics: TradeAnalysisMetrics;
  entry_points: EntryPointAnalysis[];
}

export interface Scenario {
  id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  setup_type: string;
  confidence: number;
  entry_zone_low: number;
  entry_zone_high: number;
  stop_loss_price: number;
  take_profit_prices: number[];
  status: string;
}

export interface ScenariosResponse {
  scenarios: Scenario[];
  total: number;
}

export interface LearningModel {
  id: string;
  type: string;
  version: string;
  samples_count: number;
  is_active: boolean;
  training_date: number;
}

export interface LearningModelsResponse {
  models: LearningModel[];
}
