import { describe, expect, it } from "vitest";
import { extendedPerformance } from "./performance";

const timestamp = (value: string) => Date.parse(`${value}T00:00:00Z`);

describe("extendedPerformance", () => {
  it("reports losing-month percentage, average loss, R² and recovery factor", () => {
    const metrics = extendedPerformance(100, 108.9, [
      { timestamp: timestamp("2024-01-31"), equity: 110 },
      { timestamp: timestamp("2024-02-29"), equity: 99 },
      { timestamp: timestamp("2024-03-31"), equity: 108.9 },
    ]);
    expect(metrics.averageMonthlyReturnPercent).toBeCloseTo(10 / 3);
    expect(metrics.losingMonths).toBe(1);
    expect(metrics.losingMonthsPercent).toBeCloseTo(100 / 3);
    expect(metrics.averageLosingMonthPercent).toBeCloseTo(-10);
    expect(metrics.recoveryFactor).toBeCloseTo(8.9 / 11);
    expect(metrics.equityCurveRSquared).toBeGreaterThanOrEqual(0);
    expect(metrics.equityCurveRSquared).toBeLessThanOrEqual(1);
  });

  it("handles an empty equity curve", () => {
    const metrics = extendedPerformance(100, 100, []);
    expect(metrics.averageMonthlyReturnPercent).toBe(0);
    expect(metrics.annualizedReturnPercent).toBe(0);
    expect(metrics.losingMonths).toBe(0);
    expect(metrics.recoveryFactor).toBeUndefined();
  });
});
