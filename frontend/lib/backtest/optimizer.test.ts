import { describe, expect, it } from "vitest";
import { defaultBacktestSettings } from "./defaultSettings";
import {
  assessResult,
  compareResults,
  explorationValues,
  OPTIMIZER_PARAMETERS,
  validOptimizerSettings,
} from "./optimizer";
import type { BacktestResult } from "./types";

const result = (equity: number[], overrides: Partial<BacktestResult> = {}): BacktestResult => {
  const initialCapital = 100;
  const finalCapital = equity.at(-1) ?? initialCapital;
  return {
    initialCapital,
    finalCapital,
    netProfit: finalCapital - initialCapital,
    totalReturnPercent: finalCapital - initialCapital,
    maxDrawdownPercent: 0,
    winRate: 60,
    profitFactor: 1.5,
    totalTrades: 10,
    averageTrade: 1,
    sharpeRatio: 1,
    trades: [],
    equity: equity.map((value, index) => ({ timestamp: Date.UTC(2026, index, 1), equity: value })),
    chartCandles: [],
    chartCandlesByTimeframe: {},
    scenarios: [],
    patternDiagnostics: {},
    elliottPatterns: [],
    ...overrides,
  };
};

describe("optimizer exploration", () => {
  it("starts below the regular backtest value and then searches above it", () => {
    const parameter = OPTIMIZER_PARAMETERS.find((item) => item.key === "atrPeriod")!;
    expect(explorationValues(parameter, defaultBacktestSettings)).toEqual([
      "10", "7", "20", "21", "28", "50", "100", "200",
    ]);
  });

  it("keeps the entry model first and validates coupled RR settings", () => {
    expect(OPTIMIZER_PARAMETERS[0].key).toBe("entryModel");
    expect(validOptimizerSettings(defaultBacktestSettings)).toBe(true);
    expect(validOptimizerSettings({
      ...defaultBacktestSettings,
      elliott: { ...defaultBacktestSettings.elliott, minimumRr: 3, takeProfitRr: 2 },
    })).toBe(false);
  });
});

describe("optimizer result assessment", () => {
  it("prefers a steady curve over a curve with a hard drawdown", () => {
    const steady = result([101, 103, 105, 107, 110]);
    const volatile = result([110, 80, 120, 85, 130], { maxDrawdownPercent: 33 });
    expect(assessResult(steady).curveScore).toBeGreaterThan(assessResult(volatile).curveScore);
    expect(compareResults(steady, volatile)).toBeGreaterThan(0);
  });

  it("does not punish a large upward jump when the rest of the curve remains orderly", () => {
    const withJump = result([101, 102, 120, 121, 122]);
    expect(assessResult(withJump).curveScore).toBeGreaterThan(90);
  });

  it("penalizes late slowdown mildly", () => {
    const steady = result([102, 104, 106, 108, 110, 112]);
    const slowing = result([104, 108, 112, 113, 113.5, 114]);
    const steadyAssessment = assessResult(steady);
    const slowingAssessment = assessResult(slowing);
    expect(slowingAssessment.lateSlowdown).toBeGreaterThan(0);
    expect(steadyAssessment.curveScore).toBeGreaterThan(slowingAssessment.curveScore);
    expect(slowingAssessment.curveScore).toBeGreaterThan(90);
  });

  it("uses profit factor after curve quality and profit", () => {
    const lowerFactor = result([101, 102, 103], { profitFactor: 1.2 });
    const higherFactor = result([101, 102, 103], { profitFactor: 2.1 });
    expect(compareResults(higherFactor, lowerFactor)).toBeGreaterThan(0);
  });
});
