import type { EquityPoint } from "./types";

export function extendedPerformance(initial: number, final: number, source: EquityPoint[]) {
  const equity = [...source].sort((left, right) => left.timestamp - right.timestamp);
  const monthEnds = new Map<string, number>();
  equity.forEach((point) => {
    const date = new Date(point.timestamp);
    monthEnds.set(`${date.getUTCFullYear()}-${date.getUTCMonth()}`, point.equity);
  });
  let previous = initial;
  const monthlyReturns = [...monthEnds.values()].map((value) => {
    const result = previous ? (value / previous - 1) * 100 : 0;
    previous = value;
    return result;
  });
  const losing = monthlyReturns.filter((value) => value < 0);
  const years = equity.length > 1
    ? (equity.at(-1)!.timestamp - equity[0].timestamp) / (365.2425 * 86_400_000)
    : 0;
  const annualized = initial > 0 && final >= 0
    ? (years >= 1 / 12 ? (Math.pow(final / initial, 1 / years) - 1) * 100 : (final / initial - 1) * 100)
    : 0;
  let peak = initial;
  let maxDrawdown = 0;
  equity.forEach((point) => {
    peak = Math.max(peak, point.equity);
    maxDrawdown = Math.max(maxDrawdown, peak - point.equity);
  });
  const xs = equity.map((point) => (point.timestamp - (equity[0]?.timestamp ?? 0)) / 86_400_000);
  const ys = equity.map((point) => point.equity);
  const xMean = xs.reduce((sum, value) => sum + value, 0) / (xs.length || 1);
  const yMean = ys.reduce((sum, value) => sum + value, 0) / (ys.length || 1);
  const xVariance = xs.reduce((sum, value) => sum + (value - xMean) ** 2, 0);
  const totalVariance = ys.reduce((sum, value) => sum + (value - yMean) ** 2, 0);
  let rSquared = 0;
  if (xVariance && totalVariance) {
    const slope = xs.reduce((sum, x, index) => sum + (x - xMean) * (ys[index] - yMean), 0) / xVariance;
    const residual = ys.reduce(
      (sum, y, index) => sum + (y - (yMean + slope * (xs[index] - xMean))) ** 2,
      0,
    );
    rSquared = Math.max(0, Math.min(1, 1 - residual / totalVariance));
  }
  return {
    averageMonthlyReturnPercent: monthlyReturns.reduce((sum, value) => sum + value, 0) / (monthlyReturns.length || 1),
    annualizedReturnPercent: annualized,
    losingMonths: losing.length,
    losingMonthsPercent: losing.length / (monthlyReturns.length || 1) * 100,
    averageLosingMonthPercent: losing.reduce((sum, value) => sum + value, 0) / (losing.length || 1),
    equityCurveRSquared: rSquared,
    recoveryFactor: maxDrawdown ? (final - initial) / maxDrawdown : undefined,
  };
}
