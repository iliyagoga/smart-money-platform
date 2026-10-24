import type { ClosedTrade, Position, TradingOrder } from "./types";

export interface ExecutionChartTrade {
  id: string; direction: "LONG" | "SHORT"; entry_time: number; entry_price: number;
  exit_time?: number; exit_price?: number; pnl?: number; reason?: string;
  stop?: number; targets?: number[]; mode: string; pending?: boolean;
}

export function executionChartTrades(symbol: string, positions: Position[], trades: ClosedTrade[],
  orders: TradingOrder[] = []): ExecutionChartTrade[] {
  const closedIds = new Set(trades.map((trade) => trade.position_id));
  const positionOrders = new Set(positions.map((p) => p.order_id));
  return [
    ...orders.filter((o) => o.symbol === symbol && !positionOrders.has(o.id)
      && ["PENDING", "SUBMITTING", "OPEN"].includes(o.status) && o.price != null && o.price > 0)
      .map((o) => ({ id: o.id, direction: o.side === "BUY" ? "LONG" as const : "SHORT" as const,
        entry_time: o.created_at, entry_price: o.price!, stop: o.stop_loss_price,
        targets: o.take_profit_prices, mode: o.execution_mode ?? "UNKNOWN", pending: true })),
    ...positions.filter((p) => p.symbol === symbol && p.status !== "CLOSED" && !closedIds.has(p.id)
      && p.opened_at != null).map((p) => ({ id: p.id, direction: p.direction,
      entry_time: p.opened_at!, entry_price: p.entry_price, stop: p.stop_loss_price,
      targets: p.take_profit_prices, mode: p.execution_mode ?? "UNKNOWN" })),
    ...trades.filter((t) => t.symbol === symbol && (t.direction === "LONG" || t.direction === "SHORT")
      && (t.opened_at != null || t.duration_seconds != null)).map((t) => ({
      id: t.position_id, direction: t.direction as "LONG" | "SHORT",
      entry_time: t.opened_at ?? t.closed_at - t.duration_seconds! * 1000,
      entry_price: t.entry_price, exit_time: t.closed_at, exit_price: t.exit_price,
      pnl: t.pnl, reason: t.reason, stop: t.initial_stop_loss_price,
      mode: t.execution_mode ?? "UNKNOWN",
    })),
  ].sort((a, b) => a.entry_time - b.entry_time);
}

export function marketLiveStart(config: unknown, trades: ExecutionChartTrade[], mode?: string): number | undefined {
  let value = config;
  if (typeof value === "string") { try { value = JSON.parse(value); } catch { value = undefined; } }
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const activated = Number(raw.activatedAt ?? raw.activated_at);
  const timestamps = trades.filter((trade) => mode == null || trade.mode === mode).map((trade) => trade.entry_time);
  if (Number.isFinite(activated) && activated > 0) timestamps.push(activated);
  return timestamps.length ? Math.min(...timestamps) : undefined;
}

export function riskLevelLabel(label: string, entry: number, price: number, direction: "LONG" | "SHORT"): string {
  if (!Number.isFinite(entry) || entry <= 0 || !Number.isFinite(price)) return label;
  const percent = (price - entry) / entry * 100 * (direction === "LONG" ? 1 : -1);
  return `${label} · ${percent > 0 ? "+" : ""}${percent.toFixed(2)}%`;
}
