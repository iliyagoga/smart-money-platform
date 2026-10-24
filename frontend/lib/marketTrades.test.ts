import { expect, it } from "vitest";
import { executionChartTrades, marketLiveStart, riskLevelLabel } from "./marketTrades";
import type { ClosedTrade, Position, TradingOrder } from "./types";

const position: Position = {
  id: "open", order_id: "filled-order", symbol: "BTC-USDT-SWAP", direction: "LONG", entry_price: 100,
  quantity: 1, status: "OPENED", opened_at: 100_000, execution_mode: "PRODUCTION",
  stop_loss_price: 95, take_profit_prices: [110],
};
const closed: ClosedTrade = {
  position_id: "closed", symbol: position.symbol, direction: "SHORT", entry_price: 100, exit_price: 90,
  quantity: 1, pnl: 10, reason: "TP", closed_at: 200_000, duration_seconds: 60, execution_mode: "DEMO",
};
const order: TradingOrder = {
  id: "waiting", symbol: position.symbol, side: "BUY", type: "LIMIT", price: 99,
  quantity: 1, status: "OPEN", created_at: 150_000, execution_mode: "PRODUCTION", take_profit_prices: [110],
};

it("maps actual entries, exits and pending orders without duplicating filled positions", () => {
  const result = executionChartTrades(position.symbol, [position, { ...position, symbol: "ETH-USDT-SWAP" }], [closed],
    [order, { ...order, id: "filled-order" }, { ...order, id: "rejected", status: "REJECTED" }]);
  expect(result).toHaveLength(3);
  expect(result[0]).toMatchObject({ id: "open", entry_time: 100_000, mode: "PRODUCTION", stop: 95, targets: [110] });
  expect(result[1]).toMatchObject({ id: "closed", entry_time: 140_000, exit_time: 200_000, exit_price: 90 });
  expect(result[2]).toMatchObject({ id: "waiting", pending: true });
});

it("prefers closed records over stale open positions and never invents a missing entry time", () => {
  expect(executionChartTrades(position.symbol, [{ ...position, id: "closed" }, { ...position, opened_at: undefined }],
    [closed, { ...closed, position_id: "missing-time", duration_seconds: undefined }])).toHaveLength(1);
});

it("keeps production boundary independent of earlier demo and paper executions", () => {
  const trades = executionChartTrades(position.symbol, [position], [{ ...closed, closed_at: 80_000 }]);
  expect(marketLiveStart({ activatedAt: 90_000 }, trades, "PRODUCTION")).toBe(90_000);
  expect(marketLiveStart(JSON.stringify({ activated_at: 120_000 }), trades, "PRODUCTION")).toBe(100_000);
  expect(marketLiveStart("invalid", [], "PRODUCTION")).toBeUndefined();
});

it("shows direction-adjusted price percentages without leverage or PnL assumptions", () => {
  expect(riskLevelLabel("SL", 100, 95, "LONG")).toBe("SL · -5.00%");
  expect(riskLevelLabel("TP1", 100, 110, "LONG")).toBe("TP1 · +10.00%");
  expect(riskLevelLabel("SL", 100, 105, "SHORT")).toBe("SL · -5.00%");
  expect(riskLevelLabel("TP1", 100, 90, "SHORT")).toBe("TP1 · +10.00%");
  expect(riskLevelLabel("SL", 0, 10, "LONG")).toBe("SL");
});
