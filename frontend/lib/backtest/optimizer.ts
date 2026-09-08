import type { BacktestResult, BacktestSettings, ElliottSettings } from "./types";

export type OptimizerKey = "entryModel" | "directionMode" | "atrPeriod" | "zigzagReversalAtr"
  | "minSwingAtr" | "wave1MinAtr" | "wave1MinEfficiency" | "wave2MinRetracement"
  | "wave2MaxRetracement" | "entryRetracement" | "entryExpiryBars" | "breakoutBufferAtr"
  | "retestZoneAtr" | "displacementMinAtr" | "displacementMinBodyRatio"
  | "displacementRetracement" | "sweepMinWickRatio" | "volatilityExpansionRatio"
  | "volumeExpansionRatio" | "volumeExpansionMinBodyRatio" | "chochMinAtr"
  | "chochMinBodyRatio" | "adxPeriod" | "adxMin" | "requireDiConfirmation"
  | "stopBufferAtr" | "minimumRr" | "takeProfitCount" | "takeProfitRr"
  | "secondTakeProfitRr" | "firstTakeAction" | "useMargin"
  | "reinvestProfits" | "leverage" | "riskPerTradePercent";

type Parameter = {
  key: OptimizerKey;
  label: string;
  values: Array<string | number | boolean>;
  applies?: (settings: BacktestSettings) => boolean;
};

const quarterSteps = (minimum: number, maximum: number) =>
  Array.from({ length: Math.round((maximum - minimum) / .25) + 1 }, (_, index) => minimum + index * .25);
const halfSteps = (minimum: number, maximum: number) =>
  Array.from({ length: Math.round((maximum - minimum) / .5) + 1 }, (_, index) => minimum + index * .5);

const entryModels: ElliottSettings["entryModel"][] = [
  "CHOCH_MARKET", "CHOCH_RETRACE", "WAVE1_BREAK_RETRACE", "WAVE1_BREAK_MARKET",
  "WAVE1_BREAK_STOP", "WAVE1_BREAK_RETEST_CONFIRM", "MICRO_WAVE3", "DISPLACEMENT_RETRACE",
  "P2_LIQUIDITY_SWEEP", "WAVE2_TRENDLINE_BREAK", "ADX_ACCELERATION",
  "VOLATILITY_EXPANSION", "VOLUME_EXPANSION",
];

const modelIs = (...models: ElliottSettings["entryModel"][]) => (settings: BacktestSettings) =>
  models.includes(settings.elliott.entryModel);

// Entry model is intentionally first. The remaining fields follow BacktestSettingsForm.
// Exchange costs and execution assumptions are intentionally absent from this list.
export const OPTIMIZER_PARAMETERS: readonly Parameter[] = [
  { key: "entryModel", label: "Модель входа", values: entryModels },
  { key: "directionMode", label: "Направление", values: ["BOTH", "LONG", "SHORT"] },
  { key: "atrPeriod", label: "ATR период", values: [7, 10, 14, 20, 21, 28, 50, 100, 200] },
  { key: "zigzagReversalAtr", label: "Разворот ZigZag, ATR", values: quarterSteps(.25, 10) },
  { key: "minSwingAtr", label: "Мин. swing, ATR", values: quarterSteps(0, 10) },
  { key: "wave1MinAtr", label: "Wave 1 мин., ATR", values: [0, .5, 1, 1.5, 2, 3, 5, 10, 20] },
  { key: "wave1MinEfficiency", label: "Wave 1 efficiency", values: [0, .25, .35, .45, .5, .6, .75, 1] },
  { key: "wave2MinRetracement", label: "Wave 2 retracement от", values: [0, .236, .382, .5, .618, .786] },
  { key: "wave2MaxRetracement", label: "Wave 2 retracement до", values: [.236, .382, .5, .618, .786, .9, .99] },
  { key: "entryRetracement", label: "Доля импульса от CHOCH", values: [0, .236, .382, .5, .618, .786, 1], applies: modelIs("CHOCH_RETRACE") },
  { key: "entryExpiryBars", label: "Ждать вход, свечей", values: [1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100] },
  { key: "breakoutBufferAtr", label: "Буфер пробоя P1, ATR", values: [0, .1, .2, .3], applies: modelIs("WAVE1_BREAK_MARKET", "WAVE1_BREAK_STOP") },
  { key: "retestZoneAtr", label: "Зона ретеста P1, ATR", values: [.1, .2, .25, .3, .4, .5], applies: modelIs("WAVE1_BREAK_RETEST_CONFIRM") },
  { key: "displacementMinAtr", label: "Displacement, ATR", values: [.5, .75, 1, 1.25, 1.5, 2], applies: modelIs("DISPLACEMENT_RETRACE") },
  { key: "displacementMinBodyRatio", label: "Displacement body ratio", values: [.5, .6, .65, .7, .8], applies: modelIs("DISPLACEMENT_RETRACE") },
  { key: "displacementRetracement", label: "Откат displacement", values: [.382, .5, .618], applies: modelIs("DISPLACEMENT_RETRACE") },
  { key: "sweepMinWickRatio", label: "Мин. тень sweep P2", values: [.3, .4, .5, .6], applies: modelIs("P2_LIQUIDITY_SWEEP") },
  { key: "volatilityExpansionRatio", label: "Расширение ATR", values: [1.2, 1.5, 2, 2.5], applies: modelIs("VOLATILITY_EXPANSION") },
  { key: "volumeExpansionRatio", label: "Расширение объёма", values: [1.2, 1.5, 2, 2.5, 3], applies: modelIs("VOLUME_EXPANSION") },
  { key: "volumeExpansionMinBodyRatio", label: "Volume body ratio", values: [.5, .6, .65, .7, .8], applies: modelIs("VOLUME_EXPANSION") },
  { key: "chochMinAtr", label: "CHOCH displacement, ATR", values: [0, .25, .5, .75, 1, 1.5, 2, 3, 5, 10] },
  { key: "chochMinBodyRatio", label: "Мин. тело свечи", values: [0, .25, .35, .5, .6, .75, 1] },
  { key: "adxPeriod", label: "Период ADX", values: [7, 10, 14, 20, 21, 28, 50, 100] },
  { key: "adxMin", label: "Минимальный ADX", values: [0, 10, 15, 20, 25, 30, 40, 50] },
  { key: "requireDiConfirmation", label: "Подтверждение +DI/-DI", values: [false, true] },
  { key: "stopBufferAtr", label: "Буфер стопа, ATR", values: [0, .1, .2, .25, .5, .75, 1, 1.5, 2, 3, 5, 10] },
  { key: "minimumRr", label: "Минимальный RR", values: halfSteps(.5, 5) },
  { key: "takeProfitCount", label: "Количество тейков", values: [1, 2] },
  { key: "takeProfitRr", label: "TP1, RR", values: halfSteps(.5, 5) },
  { key: "secondTakeProfitRr", label: "TP2, RR", values: halfSteps(.5, 5), applies: (settings) => settings.elliott.takeProfitCount === 2 },
  { key: "firstTakeAction", label: "Действие на TP1", values: ["PARTIAL_CLOSE", "MOVE_TO_BREAK_EVEN"], applies: (settings) => settings.elliott.takeProfitCount === 2 },
  // Risk is evaluated before leverage because leverage may not exceed the selected risk percentage.
  { key: "riskPerTradePercent", label: "Риск на сделку, %", values: [1, 2, 3, 4, 5] },
  { key: "useMargin", label: "Режим позиции", values: [false, true] },
  { key: "reinvestProfits", label: "Реинвестирование прибыли", values: [false, true] },
  { key: "leverage", label: "Плечо и маржа", values: [1, 2, 3, 4, 5] },
] as const;

const rootKeys = new Set<OptimizerKey>(["directionMode", "leverage", "riskPerTradePercent"]);
const stringKeys = new Set<OptimizerKey>(["entryModel", "directionMode", "firstTakeAction"]);
const booleanKeys = new Set<OptimizerKey>(["requireDiConfirmation", "useMargin", "reinvestProfits"]);

export function getOptimizerValue(settings: BacktestSettings, key: OptimizerKey): string {
  return String(rootKeys.has(key)
    ? settings[key as "directionMode" | "leverage" | "riskPerTradePercent"]
    : settings.elliott[key as keyof ElliottSettings]);
}

export function setOptimizerValue(settings: BacktestSettings, key: OptimizerKey, raw: string): BacktestSettings {
  const value: string | number | boolean = booleanKeys.has(key)
    ? raw === "true"
    : stringKeys.has(key) ? raw : Number(raw);
  const updated = rootKeys.has(key)
    ? { ...settings, [key]: value } as BacktestSettings
    : { ...settings, elliott: { ...settings.elliott, [key]: value } as ElliottSettings };
  if (key === "leverage" && Number(value) > 1) {
    return { ...updated, elliott: { ...updated.elliott, useMargin: true } };
  }
  return updated.elliott.useMargin ? updated : { ...updated, leverage: 1 };
}

export function parameterApplies(parameter: Parameter, settings: BacktestSettings): boolean {
  return parameter.applies?.(settings) ?? true;
}

export function explorationValues(parameter: Parameter, settings: BacktestSettings): string[] {
  const current = getOptimizerValue(settings, parameter.key);
  const values = [...new Set(parameter.values.map(String))];
  if (!values.includes(current)) {
    if (!Number.isNaN(Number(current)) && values.every((value) => !Number.isNaN(Number(value)))) {
      values.push(current);
      values.sort((left, right) => Number(left) - Number(right));
    } else {
      values.unshift(current);
    }
  }
  const currentIndex = values.indexOf(current);
  return [
    ...values.slice(0, currentIndex).reverse(),
    ...values.slice(currentIndex + 1),
  ];
}

export function validOptimizerSettings(settings: BacktestSettings): boolean {
  const timeframeRank: Record<string, number> = { M1: 1, M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440 };
  const elliott = settings.elliott;
  return settings.initialCapital > 0
    && settings.leverage >= 1
    && settings.riskPerTradePercent >= 0
    && (!elliott.useMargin || settings.leverage <= settings.riskPerTradePercent)
    && timeframeRank[elliott.entryTimeframe] < timeframeRank[elliott.structureTimeframe]
    && timeframeRank[elliott.structureTimeframe] < timeframeRank[elliott.macroTimeframe]
    && elliott.wave2MinRetracement < elliott.wave2MaxRetracement
    && elliott.takeProfitRr >= elliott.minimumRr
    && (elliott.takeProfitCount === 1 || elliott.secondTakeProfitRr > elliott.takeProfitRr);
}

export interface ResultAssessment {
  curveScore: number;
  curveDeviationPercent: number;
  lateSlowdown: number;
  losingMonths: number;
  profitFactor: number;
  totalReturnPercent: number;
  winRate: number;
  sharpeRatio: number;
  hasTrades: boolean;
  profitable: boolean;
}

export interface OptimizationRequirements {
  minimumTrades: number;
  minimumProfitPercent: number;
  maximumLosingMonths: number;
}

export const DEFAULT_OPTIMIZATION_REQUIREMENTS: OptimizationRequirements = {
  minimumTrades: 3,
  minimumProfitPercent: 0,
  maximumLosingMonths: 2,
};

const clamp = (value: number, minimum = 0, maximum = 1) => Math.min(maximum, Math.max(minimum, value));

function countLosingMonths(result: BacktestResult): number {
  const monthlyCloses = new Map<string, number>();
  for (const point of [...result.equity].sort((left, right) => left.timestamp - right.timestamp)) {
    monthlyCloses.set(new Date(point.timestamp).toISOString().slice(0, 7), point.equity);
  }
  let previous = result.initialCapital;
  let losingMonths = 0;
  for (const equity of monthlyCloses.values()) {
    if (equity < previous) losingMonths += 1;
    previous = equity;
  }
  return losingMonths;
}

export function assessResult(result: BacktestResult): ResultAssessment {
  const points = [...result.equity].sort((left, right) => left.timestamp - right.timestamp);
  const equity = points.map((point) => point.equity);
  const values = [result.initialCapital, ...equity];
  const endingCapital = values.at(-1) ?? result.finalCapital;
  const totalMove = endingCapital - result.initialCapital;
  const inferredStep = points.length > 1 ? points[1].timestamp - points[0].timestamp : 1;
  const startTime = result.dataset?.testFrom ?? ((points[0]?.timestamp ?? 1) - inferredStep);
  const endTime = result.dataset?.testTo ?? points.at(-1)?.timestamp ?? startTime + 1;
  const duration = Math.max(1, endTime - startTime);
  const capitalScale = Math.max(Math.abs(totalMove), Math.abs(result.initialCapital) * .01, 1e-12);
  const normalizedEnd = totalMove / capitalScale;
  const lineLength = Math.sqrt(1 + normalizedEnd ** 2);
  const perpendicularDistances = points.map((point) => {
    const normalizedTime = clamp((point.timestamp - startTime) / duration);
    const normalizedCapital = (point.equity - result.initialCapital) / capitalScale;
    return Math.abs(normalizedEnd * normalizedTime - normalizedCapital) / lineLength;
  });
  const rootMeanSquaredDistance = Math.sqrt(
    perpendicularDistances.reduce((sum, distance) => sum + distance ** 2, 0)
      / Math.max(1, perpendicularDistances.length),
  );
  const curveDeviationPercent = rootMeanSquaredDistance * 100;
  const curveScore = Math.exp(-.5 * (rootMeanSquaredDistance / .1) ** 2) * 100;
  const netGrowth = values.length > 1
    ? (values.at(-1)! - values[0]) / Math.max(Math.abs(values[0]), 1e-12)
    : result.totalReturnPercent / 100;
  const recentStart = Math.max(0, Math.floor((values.length - 1) * 2 / 3));
  const overallPerStep = netGrowth / Math.max(1, values.length - 1);
  const recentGrowth = values.length > 1
    ? (values.at(-1)! - values[recentStart]) / Math.max(Math.abs(values[recentStart]), 1e-12)
    : 0;
  const recentPerStep = recentGrowth / Math.max(1, values.length - 1 - recentStart);
  const lateSlowdown = overallPerStep > 0 ? clamp((overallPerStep - recentPerStep) / overallPerStep) : 0;
  const hasTrades = result.totalTrades > 0;
  const profitable = hasTrades && result.totalReturnPercent > 0;
  const profitFactor = result.profitFactor ?? (profitable ? Number.POSITIVE_INFINITY : 0);
  return {
    curveScore,
    curveDeviationPercent,
    lateSlowdown,
    losingMonths: countLosingMonths(result),
    profitFactor,
    totalReturnPercent: result.totalReturnPercent,
    winRate: result.winRate,
    sharpeRatio: result.sharpeRatio ?? 0,
    hasTrades,
    profitable,
  };
}

const compareNumber = (left: number, right: number, tolerance = 1e-9) => {
  if (Object.is(left, right) || Math.abs(left - right) <= tolerance) return 0;
  return left > right ? 1 : -1;
};

export function meetsOptimizationRequirements(
  result: BacktestResult,
  requirements: OptimizationRequirements,
): boolean {
  return result.totalTrades >= requirements.minimumTrades
    && result.totalReturnPercent >= requirements.minimumProfitPercent
    && countLosingMonths(result) <= requirements.maximumLosingMonths;
}

export function compareResults(left: BacktestResult, right: BacktestResult): number {
  const a = assessResult(left);
  const b = assessResult(right);
  const comparisons = [
    compareNumber(a.totalReturnPercent, b.totalReturnPercent),
    compareNumber(a.curveScore, b.curveScore, .05),
    compareNumber(-a.losingMonths, -b.losingMonths),
    compareNumber(a.profitFactor, b.profitFactor),
    compareNumber(a.winRate, b.winRate),
    compareNumber(a.sharpeRatio, b.sharpeRatio),
  ];
  return comparisons.find((comparison) => comparison !== 0) ?? 0;
}

export function isBetterEligibleResult(
  candidate: BacktestResult,
  current: BacktestResult,
  requirements: OptimizationRequirements,
): boolean {
  if (!meetsOptimizationRequirements(candidate, requirements)) return false;
  if (!meetsOptimizationRequirements(current, requirements)) return true;
  return compareResults(candidate, current) > 0;
}

export function isGoodStageResult(
  candidate: BacktestResult,
  baseline: BacktestResult,
  requirements: OptimizationRequirements = DEFAULT_OPTIMIZATION_REQUIREMENTS,
): boolean {
  if (!isBetterEligibleResult(candidate, baseline, requirements)) return false;
  const assessment = assessResult(candidate);
  return assessment.profitable
    && assessment.curveScore >= 60
    && candidate.maxDrawdownPercent <= 25;
}
