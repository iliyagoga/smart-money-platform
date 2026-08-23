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
  quantity: number;
  status: string;
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
