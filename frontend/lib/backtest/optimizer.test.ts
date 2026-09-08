import { describe, expect, it } from "vitest";
import { defaultBacktestSettings } from "./defaultSettings";
import {
  assessResult,
  compareResults,
  DEFAULT_OPTIMIZATION_REQUIREMENTS,
  explorationValues,
  isBetterEligibleResult,
  isGoodStageResult,
  meetsOptimizationRequirements,
  optimizationPeriod,
  OPTIMIZATION_PERIOD_SHARE,
  OPTIMIZER_PARAMETERS,
  setOptimizerValue,
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
    averageMonthlyReturnPercent: 0,
    annualizedReturnPercent: 0,
    losingMonths: 0,
    losingMonthsPercent: 0,
    averageLosingMonthPercent: 0,
    equityCurveRSquared: 0,
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
  it("uses the first 70 percent for optimization", () => {
    expect(OPTIMIZATION_PERIOD_SHARE).toBe(.7);
    expect(optimizationPeriod("2026-01-01", "2026-01-11")).toEqual({
      from: "2026-01-01",
      to: "2026-01-08",
    });
  });

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

  it("does not optimize capital and uses 0.5 steps for every RR parameter", () => {
    expect(OPTIMIZER_PARAMETERS.map((parameter) => String(parameter.key))).not.toContain("initialCapital");
    for (const key of ["minimumRr", "takeProfitRr", "secondTakeProfitRr"] as const) {
      const parameter = OPTIMIZER_PARAMETERS.find((item) => item.key === key)!;
      expect(parameter.values).toEqual([.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5]);
    }
  });

  it("enables margin while exploring leverage and changes risk independently", () => {
    const riskAdjusted = setOptimizerValue(defaultBacktestSettings, "riskPerTradePercent", "5");
    const leveraged = setOptimizerValue(riskAdjusted, "leverage", "5");
    expect(leveraged.elliott.useMargin).toBe(true);
    expect(leveraged.leverage).toBe(5);
    expect(riskAdjusted.riskPerTradePercent).toBe(5);
    expect(validOptimizerSettings(leveraged)).toBe(true);
  });

  it("never allows leverage to exceed risk", () => {
    const riskAdjusted = setOptimizerValue(defaultBacktestSettings, "riskPerTradePercent", "3");
    const excessiveLeverage = setOptimizerValue(riskAdjusted, "leverage", "4");
    expect(excessiveLeverage.elliott.useMargin).toBe(true);
    expect(validOptimizerSettings(excessiveLeverage)).toBe(false);
  });

  it("uses the requested 1 to 5 ranges and evaluates risk before leverage", () => {
    const riskIndex = OPTIMIZER_PARAMETERS.findIndex((parameter) => parameter.key === "riskPerTradePercent");
    const leverageIndex = OPTIMIZER_PARAMETERS.findIndex((parameter) => parameter.key === "leverage");
    expect(OPTIMIZER_PARAMETERS[riskIndex].values).toEqual([1, 2, 3, 4, 5]);
    expect(OPTIMIZER_PARAMETERS[leverageIndex].values).toEqual([1, 2, 3, 4, 5]);
    expect(riskIndex).toBeLessThan(leverageIndex);
  });
});

describe("optimizer result assessment", () => {
  it("uses curve quality when final profit is equal", () => {
    const steady = result([101, 103, 105, 107, 110]);
    const volatile = result([105, 90, 115, 95, 110], { maxDrawdownPercent: 22 });
    expect(assessResult(steady).curveScore).toBeGreaterThan(assessResult(volatile).curveScore);
    expect(compareResults(steady, volatile)).toBeGreaterThan(0);
  });

  it("uses final profit as the primary assessment criterion", () => {
    const smoother = result([102, 104, 106, 108, 110]);
    const moreProfitable = result([110, 102, 115], { maxDrawdownPercent: 8 });
    expect(assessResult(smoother).curveScore).toBeGreaterThan(assessResult(moreProfitable).curveScore);
    expect(compareResults(moreProfitable, smoother)).toBeGreaterThan(0);
  });

  it("prefers points that stay close to the start-to-finish line", () => {
    const straight = result([104.4, 108.8, 113.2, 117.6, 122]);
    const withJump = result([101, 102, 120, 121, 122]);
    expect(assessResult(straight).curveScore).toBeGreaterThan(99.9);
    expect(assessResult(straight).curveScore).toBeGreaterThan(assessResult(withJump).curveScore);
  });

  it("penalizes late slowdown mildly", () => {
    const steady = result([102, 104, 106, 108, 110, 112]);
    const slowing = result([104, 108, 112, 113, 113.5, 114]);
    const steadyAssessment = assessResult(steady);
    const slowingAssessment = assessResult(slowing);
    expect(slowingAssessment.lateSlowdown).toBeGreaterThan(0);
    expect(steadyAssessment.curveScore).toBeGreaterThan(slowingAssessment.curveScore);
    expect(slowingAssessment.curveDeviationPercent).toBeGreaterThan(0);
  });

  it("uses profit factor after curve quality and profit", () => {
    const lowerFactor = result([101, 102, 103], { profitFactor: 1.2 });
    const higherFactor = result([101, 102, 103], { profitFactor: 2.1 });
    expect(compareResults(higherFactor, lowerFactor)).toBeGreaterThan(0);
  });

  it("does not accept a smooth result based on only one trade", () => {
    const baseline = result([100, 100, 100], { totalTrades: 0, winRate: 0, profitFactor: 0 });
    const oneTrade = result([100, 110, 120], { totalTrades: 1, winRate: 100, profitFactor: 10 });
    expect(meetsOptimizationRequirements(oneTrade, DEFAULT_OPTIMIZATION_REQUIREMENTS)).toBe(false);
    expect(isGoodStageResult(oneTrade, baseline)).toBe(false);
  });

  it("uses minimum profit and maximum losing months as hard requirements", () => {
    const requirements = { minimumTrades: 3, minimumProfitPercent: 5, maximumLosingMonths: 1 };
    const lowProfit = result([100, 102, 104], { totalTrades: 20 });
    const tooManyLosingMonths = result([110, 105, 101, 120], { totalTrades: 20 });
    const accepted = result([102, 108, 112], { totalTrades: 20 });
    expect(meetsOptimizationRequirements(lowProfit, requirements)).toBe(false);
    expect(meetsOptimizationRequirements(tooManyLosingMonths, requirements)).toBe(false);
    expect(meetsOptimizationRequirements(accepted, requirements)).toBe(true);
  });

  it("filters candidates before comparing their quality", () => {
    const requirements = { minimumTrades: 3, minimumProfitPercent: 5, maximumLosingMonths: 1 };
    const oneTrade = result([110, 120, 130], { totalTrades: 1, profitFactor: 20 });
    const qualified = result([101, 99, 108], { totalTrades: 8, maxDrawdownPercent: 2 });
    expect(compareResults(oneTrade, qualified)).toBeGreaterThan(0);
    expect(isBetterEligibleResult(qualified, oneTrade, requirements)).toBe(true);
    expect(isBetterEligibleResult(oneTrade, qualified, requirements)).toBe(false);
  });
});
