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
  payload?: { symbol?: string };
}

export interface ServicesResponse {
  services?: ServiceStatus[];
}

export interface PositionsResponse {
  positions?: Position[];
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
