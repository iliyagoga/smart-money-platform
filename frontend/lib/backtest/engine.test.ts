import { describe, expect, it } from "vitest";
import { runBacktest } from "./engine";
import type { BacktestSettings } from "./types";
import type { Candle } from "../types";

const settings: BacktestSettings = {
  initialCapital: 10_000,
  strategy: "SMA_CROSS",
  fastPeriod: 2,
  slowPeriod: 3,
  feePercent: 0,
  slippagePercent: 0,
  stopLossPercent: 20,
  takeProfitPercent: 20,
  positionSizePercent: 100,
  leverage: 1,
  fundingPercentPerDay: 0,
  directionMode: "BOTH",
};

const candles = (closes: number[]): Candle[] => closes.map((close, index) => ({
  timestamp: index * 60_000,
  open: close,
  high: close,
  low: close,
  close,
  volume: 1,
}));

describe("backtest engine", () => {
  it("does not create trades on a flat market", () => {
    const result = runBacktest({ candles: candles([10, 10, 10, 10, 10, 10]), settings });
    expect(result.totalTrades).toBe(0);
    expect(result.finalCapital).toBe(10_000);
  });

  it("executes crossover signals and produces an equity curve", () => {
    const result = runBacktest({ candles: candles([10, 9, 10, 12, 14, 13, 11, 9, 8]), settings });
    expect(result.totalTrades).toBeGreaterThan(0);
    expect(result.equity.length).toBeGreaterThan(1);
    expect(Number.isFinite(result.maxDrawdownPercent)).toBe(true);
  });

  it("applies trading fees", () => {
    const withoutFees = runBacktest({ candles: candles([10, 9, 10, 12, 14, 13, 11, 9, 8]), settings });
    const withFees = runBacktest({
      candles: candles([10, 9, 10, 12, 14, 13, 11, 9, 8]),
      settings: { ...settings, feePercent: 0.2 },
    });
    expect(withFees.finalCapital).toBeLessThan(withoutFees.finalCapital);
  });
});
