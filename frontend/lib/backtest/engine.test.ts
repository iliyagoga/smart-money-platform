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
  maintenanceMarginPercent: 0.5,
  fundingPercentPerDay: 0,
  directionMode: "BOTH",
  riskPerTradePercent: 1,
  smcTargetMode: "TEMPLATE",
  smcTargetRr: 1.5,
  smcMinTargetRr: 1.5,
  smcMaxTargetRr: 8,
  kellyFraction: 0.25,
  confidenceThreshold: 0.6,
  templateIds: ["OB_FVG_REVERSAL"],
  localRetraining: false,
  elliott: {
    macroTimeframe: "H4", structureTimeframe: "H1", entryTimeframe: "M15", atrPeriod: 14,
    zigzagReversalAtr: 1.5, minSwingAtr: 1, wave1MinAtr: 1.5, wave1MinEfficiency: 0.45,
    wave2MinRetracement: 0.382, wave2MaxRetracement: 0.786, entryModel: "CHOCH_RETRACE",
    entryRetracement: 0.5, chochMinAtr: 0.5, chochMinBodyRatio: 0.5,
    macroFilter: "STRUCTURE", stopBufferAtr: 0.2, takeProfitRr: 2, minimumRr: 1.5, breakEvenAtOneR: true,
  },
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
