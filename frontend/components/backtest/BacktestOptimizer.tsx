"use client";

import { Alert, Button, Checkbox, FormControl, FormControlLabel, FormGroup, FormHelperText, InputLabel, LinearProgress, ListItemText, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../../lib/api";
import type { BacktestResult, BacktestSettings, ElliottSettings } from "../../lib/backtest/types";

type Metric = "RETURN_DD" | "RETURN" | "PROFIT_FACTOR";
type OptimizationMode = "CASCADE" | "EXACT_GRAPH";
type Period = { from: string; to: string };
type Candidate = { settings: BacktestSettings; label: string };
type Row = Candidate & { optimization: BacktestResult; validation?: BacktestResult; optimizationScore: number; score?: number; passed?: boolean };
type Key = "directionMode" | "macroTimeframe" | "structureTimeframe" | "entryTimeframe" | "atrPeriod" | "zigzagReversalAtr" | "minSwingAtr" | "wave1MinAtr" | "wave1MinEfficiency" | "wave2MinRetracement" | "wave2MaxRetracement" | "entryModel" | "entryRetracement" | "entryExpiryBars" | "breakoutBufferAtr" | "retestZoneAtr" | "displacementMinAtr" | "displacementMinBodyRatio" | "displacementRetracement" | "sweepMinWickRatio" | "volatilityExpansionRatio" | "volumeExpansionRatio" | "volumeExpansionMinBodyRatio" | "chochMinAtr" | "chochMinBodyRatio" | "adxPeriod" | "adxMin" | "requireDiConfirmation" | "stopBufferAtr" | "exitModel" | "levelLookbackBars" | "volumeProfileBins" | "minimumRr" | "takeProfitCount" | "takeProfitRr" | "secondTakeProfitRr" | "firstTakeAction" | "initialCapital" | "useMargin" | "leverage" | "reinvestProfits" | "riskPerTradePercent";
type BlockId = "context" | "wave" | "entry" | "protection" | "capital";
type Parameter = { key: Key; label: string; options: string[] };
type Block = { id: BlockId; title: string; description: string; parameters: Parameter[] };
type Timing = { runs: number; elapsedMs: number };
type Checkpoint = { phase: "OPTIMIZATION" | "VALIDATION"; blockIndex?: number; offset: number; base?: BacktestSettings; completed: Row[]; finalists: Row[]; validationIndex: number; timings?: Record<string, Timing> };
type OptimizationConfiguration = {
  optimizationMode: OptimizationMode; metric: Metric; asset: string; timeframes: string[];
  optimizationPeriod: Period; validationPeriod: Period; validationCount: number;
  minimumTrades: number; minimumReturn: number; maximumDrawdown: number; order: BlockId[];
  enabled: Record<BlockId, boolean>; selected: Record<Key, string[]>; settings: BacktestSettings;
};
type OptimizationSession = {
  id: string; status: "RUNNING" | "PAUSED" | "CANCELLED"; configuration: OptimizationConfiguration;
  checkpoint: Checkpoint; updated_at: string; error?: string;
};

const strings = (items: Array<string | number | boolean>) => items.map(String);
const quarter = (min: number, max: number) => strings(Array.from({ length: Math.round((max - min) / .25) + 1 }, (_, i) => min + i * .25));
const tenths = (min: number, max: number) => strings(Array.from(
  { length: Math.round((max - min) * 10) + 1 },
  (_, index) => Number((min + index / 10).toFixed(1)),
));
const product = <T,>(groups: T[][]): T[][] => groups.reduce<T[][]>((rows, group) => rows.flatMap(row => group.map(item => [...row, item])), [[]]);
const score = (result: BacktestResult, metric: Metric) => metric === "RETURN" ? result.totalReturnPercent : metric === "PROFIT_FACTOR" ? result.profitFactor ?? 0 : result.totalReturnPercent - result.maxDrawdownPercent;
const compactResult = (result: BacktestResult): BacktestResult => ({
  ...result,
  trades: [],
  equity: [],
  chartCandles: [],
  chartCandlesByTimeframe: {},
  elliottPatterns: [],
});
const compactRow = (row: Row): Row => ({
  ...row,
  optimization: compactResult(row.optimization),
  validation: row.validation ? compactResult(row.validation) : undefined,
});
const checkpointForStorage = (checkpoint: Checkpoint): Checkpoint => ({
  ...checkpoint,
  completed: checkpoint.completed.map(compactRow),
  finalists: checkpoint.finalists.map(compactRow),
});
const day = (value: number) => new Date(value).toISOString().slice(0, 10);
const defaultPeriods = (from: string, to: string) => {
  const start = Date.parse(`${from}T00:00:00Z`); const end = Date.parse(`${to}T00:00:00Z`);
  const split = start + Math.floor((end - start) * .7 / 86_400_000) * 86_400_000;
  return { optimization: { from, to: day(split) }, validation: { from: day(split + 86_400_000), to } };
};
const blocks: Block[] = [
  { id: "context", title: "Контекст и таймфреймы", description: "Направление рынка, роли таймфреймов и ATR.", parameters: [
    { key: "directionMode", label: "Направление", options: ["BOTH", "LONG", "SHORT"] },
    { key: "macroTimeframe", label: "Macro TF", options: ["H1", "H4", "D1"] },
    { key: "structureTimeframe", label: "Structure TF", options: ["M15", "M30", "H1", "H4"] },
    { key: "entryTimeframe", label: "Entry TF", options: ["M1", "M5", "M15", "M30"] },
    { key: "atrPeriod", label: "ATR период", options: strings([7, 10, 14, 20, 21, 28, 50, 100, 200]) },
  ] },
  { id: "wave", title: "ZigZag и волны", description: "Геометрия ZigZag, Wave 1 и Wave 2.", parameters: [
    { key: "zigzagReversalAtr", label: "Разворот ZigZag, ATR", options: quarter(.25, 10) },
    { key: "minSwingAtr", label: "Мин. swing, ATR", options: quarter(0, 10) },
    { key: "wave1MinAtr", label: "Wave 1 мин., ATR", options: strings([0, .5, 1, 1.5, 2, 3, 5, 10, 20]) },
    { key: "wave1MinEfficiency", label: "Wave 1 efficiency", options: strings([0, .25, .35, .45, .5, .6, .75, 1]) },
    { key: "wave2MinRetracement", label: "Wave 2 от", options: strings([0, .236, .382, .5, .618, .786]) },
    { key: "wave2MaxRetracement", label: "Wave 2 до", options: strings([.236, .382, .5, .618, .786, .9, .99]) },
  ] },
  { id: "entry", title: "Вход и подтверждение", description: "Модель входа, CHOCH, срок ожидания, ADX и DI.", parameters: [
    { key: "entryModel", label: "Модель входа", options: [
      "CHOCH_MARKET", "CHOCH_RETRACE", "WAVE1_BREAK_RETRACE", "WAVE1_BREAK_MARKET", "WAVE1_BREAK_STOP",
      "WAVE1_BREAK_RETEST_CONFIRM", "MICRO_WAVE3", "DISPLACEMENT_RETRACE", "P2_LIQUIDITY_SWEEP",
      "WAVE2_TRENDLINE_BREAK", "ADX_ACCELERATION", "VOLATILITY_EXPANSION", "VOLUME_EXPANSION",
    ] },
    { key: "entryRetracement", label: "Доля импульса CHOCH", options: strings([0, .236, .382, .5, .618, .786, 1]) },
    { key: "entryExpiryBars", label: "Ждать вход, свечей", options: strings([1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100]) },
    { key: "breakoutBufferAtr", label: "Буфер P1, ATR", options: strings([0, .1, .2, .3]) },
    { key: "retestZoneAtr", label: "Ретест P1, ATR", options: strings([.1, .2, .3, .4, .5]) },
    { key: "displacementMinAtr", label: "Displacement, ATR", options: strings([.5, .75, 1, 1.25, 1.5, 2]) },
    { key: "displacementMinBodyRatio", label: "Displacement body", options: strings([.5, .6, .65, .7, .8]) },
    { key: "displacementRetracement", label: "Откат displacement", options: strings([.382, .5, .618]) },
    { key: "sweepMinWickRatio", label: "Тень sweep P2", options: strings([.3, .4, .5, .6]) },
    { key: "volatilityExpansionRatio", label: "Расширение ATR", options: strings([1.2, 1.5, 2, 2.5]) },
    { key: "volumeExpansionRatio", label: "Объём / SMA20", options: strings([1.2, 1.5, 2, 2.5, 3]) },
    { key: "volumeExpansionMinBodyRatio", label: "Volume body", options: strings([.5, .6, .65, .7, .8]) },
    { key: "chochMinAtr", label: "CHOCH displacement, ATR", options: strings([0, .25, .5, .75, 1, 1.5, 2, 3, 5, 10]) },
    { key: "chochMinBodyRatio", label: "Мин. тело свечи", options: strings([0, .25, .35, .5, .6, .75, 1]) },
    { key: "adxPeriod", label: "Период ADX", options: strings([7, 10, 14, 20, 21, 28, 50, 100]) },
    { key: "adxMin", label: "Минимальный ADX", options: strings([0, 10, 15, 20, 25, 30, 40, 50]) },
    { key: "requireDiConfirmation", label: "Подтверждение +DI/-DI", options: ["false", "true"] },
  ] },
  { id: "protection", title: "Stop Loss и Risk/Reward", description: "Структурный стоп, RR и управление тейками.", parameters: [
    { key: "exitModel", label: "Модель выхода", options: ["FIXED_RR", "LIQUIDITY_WAVE_VOLUME"] },
    { key: "stopBufferAtr", label: "Буфер стопа, ATR", options: strings([0, .1, .2, .25, .5, .75, 1, 1.5, 2, 3, 5, 10]) },
    { key: "minimumRr", label: "Минимальный RR", options: tenths(.1, 10) },
    { key: "takeProfitCount", label: "Количество тейков", options: ["1", "2"] },
    { key: "takeProfitRr", label: "TP1, RR", options: strings([.5, 1, 1.5, 2, 3, 4, 5, 8, 10]) },
    { key: "secondTakeProfitRr", label: "TP2, RR", options: strings([1, 1.5, 2, 3, 4, 5, 8, 10, 20]) },
    { key: "firstTakeAction", label: "Действие на TP1", options: ["PARTIAL_CLOSE", "MOVE_TO_BREAK_EVEN"] },
  ] },
  { id: "capital", title: "Капитал и риск", description: "Капитал, маржа, плечо, реинвестирование и риск на сделку.", parameters: [
    { key: "initialCapital", label: "Начальный капитал", options: strings([100, 500, 1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 1_000_000]) },
    { key: "useMargin", label: "Использовать маржу", options: ["false", "true"] },
    { key: "leverage", label: "Плечо", options: strings([1, 2, 3, 5, 10, 20, 50, 100]) },
    { key: "reinvestProfits", label: "Реинвестирование", options: ["false", "true"] },
    { key: "riskPerTradePercent", label: "Риск на сделку, %", options: strings([0, .25, .5, 1, 1.5, 2, 3, 5, 10]) },
  ] },
];
const blockMap = new Map(blocks.map(block => [block.id, block]));
const PARALLEL_BATCH_SIZE = 4;
const ESTIMATED_SEQUENTIAL_RUN_SECONDS = 3;
const ESTIMATED_BATCH_SECONDS = ESTIMATED_SEQUENTIAL_RUN_SECONDS;
const estimatedBlockSeconds = (count: number) => Math.ceil(count / PARALLEL_BATCH_SIZE) * ESTIMATED_BATCH_SECONDS;
const estimatedFromTiming = (count: number, timing?: Timing, parallel = true) => timing?.runs
  ? Math.ceil(count / (parallel ? PARALLEL_BATCH_SIZE : 1)) * timing.elapsedMs / timing.runs / 1000
  : parallel ? estimatedBlockSeconds(count) : count * ESTIMATED_SEQUENTIAL_RUN_SECONDS;
const formatDuration = (seconds: number) => {
  if (seconds < 60) return `≈ ${seconds} сек`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  if (hours) return `≈ ${hours} ч ${minutes} мин`;
  return `≈ ${minutes} мин`;
};
const rootKeys = new Set<Key>(["directionMode", "initialCapital", "leverage", "riskPerTradePercent"]);
const stringKeys = new Set<Key>([
  "directionMode", "macroTimeframe", "structureTimeframe", "entryTimeframe", "entryModel", "exitModel", "firstTakeAction",
]);
const booleanKeys = new Set<Key>(["requireDiConfirmation", "useMargin", "reinvestProfits"]);
const entryModelParameters: Partial<Record<ElliottSettings["entryModel"], Set<Key>>> = {
  CHOCH_RETRACE: new Set(["entryRetracement"]),
  WAVE1_BREAK_MARKET: new Set(["breakoutBufferAtr"]),
  WAVE1_BREAK_STOP: new Set(["breakoutBufferAtr"]),
  WAVE1_BREAK_RETEST_CONFIRM: new Set(["retestZoneAtr"]),
  DISPLACEMENT_RETRACE: new Set(["displacementMinAtr", "displacementMinBodyRatio", "displacementRetracement"]),
  P2_LIQUIDITY_SWEEP: new Set(["sweepMinWickRatio"]),
  VOLATILITY_EXPANSION: new Set(["volatilityExpansionRatio"]),
  VOLUME_EXPANSION: new Set(["volumeExpansionRatio", "volumeExpansionMinBodyRatio"]),
};
const commonEntryParameters = new Set<Key>([
  "entryExpiryBars", "chochMinAtr", "chochMinBodyRatio", "adxPeriod", "adxMin", "requireDiConfirmation",
]);
const parametersForEntryModel = (block: Block, model: ElliottSettings["entryModel"]) => block.parameters.filter(parameter =>
  parameter.key === "entryModel" || commonEntryParameters.has(parameter.key)
    || entryModelParameters[model]?.has(parameter.key),
);
const getValue = (settings: BacktestSettings, key: Key) => String(rootKeys.has(key) ? settings[key as "initialCapital"] : settings.elliott[key as keyof ElliottSettings]);
function setValue(settings: BacktestSettings, key: Key, raw: string): BacktestSettings {
  const value: string | number | boolean = booleanKeys.has(key) ? raw === "true" : stringKeys.has(key) ? raw : Number(raw);
  if (rootKeys.has(key)) return { ...settings, [key]: value } as BacktestSettings;
  return { ...settings, elliott: { ...settings.elliott, [key]: value } as ElliottSettings };
}
function valid(settings: BacktestSettings) {
  const e = settings.elliott;
  const timeframeRank: Record<string, number> = { M1: 1, M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440 };
  return settings.initialCapital > 0 && settings.leverage >= 1 && settings.riskPerTradePercent >= 0
    && timeframeRank[e.entryTimeframe] < timeframeRank[e.structureTimeframe]
    && timeframeRank[e.structureTimeframe] < timeframeRank[e.macroTimeframe]
    && e.wave2MinRetracement < e.wave2MaxRetracement && e.minimumRr > 0
    && e.takeProfitRr >= e.minimumRr
    && (e.takeProfitCount === 1 || e.secondTakeProfitRr > e.takeProfitRr);
}

interface Props {
  settings: BacktestSettings; assets: string[]; initialAsset: string; initialTimeframes: string[];
  testFrom: string; testTo: string;
  onApply: (settings: BacktestSettings, result: BacktestResult) => void;
  runCandidate: (settings: BacktestSettings, period: Period, asset: string, timeframes: string[], summary?: boolean) => Promise<BacktestResult>;
}

export function BacktestOptimizer({ settings, assets, initialAsset, initialTimeframes, testFrom, testTo, onApply, runCandidate }: Props) {
  const defaults = defaultPeriods(testFrom, testTo);
  const [optimizationMode, setOptimizationMode] = useState<OptimizationMode>("CASCADE");
  const [metric, setMetric] = useState<Metric>("RETURN_DD");
  const [asset, setAsset] = useState(initialAsset);
  const [timeframes, setTimeframes] = useState(initialTimeframes);
  const [optimizationPeriod, setOptimizationPeriod] = useState(defaults.optimization);
  const [validationPeriod, setValidationPeriod] = useState(defaults.validation);
  const [validationCount, setValidationCount] = useState(5);
  const [minimumTrades, setMinimumTrades] = useState(3);
  const [minimumReturn, setMinimumReturn] = useState(0);
  const [maximumDrawdown, setMaximumDrawdown] = useState(30);
  const [running, setRunning] = useState(false); const [stage, setStage] = useState("Перебор"); const [done, setDone] = useState(0); const [total, setTotal] = useState(0); const [rows, setRows] = useState<Row[]>([]); const [error, setError] = useState("");
  const [savedSession, setSavedSession] = useState<OptimizationSession | null>(null);
  const [savedTopCount, setSavedTopCount] = useState(0);
  const [timings, setTimings] = useState<Record<string, Timing>>({});
  const [lastSavedAt, setLastSavedAt] = useState<string>();
  const controlRequested = useRef<"PAUSE" | "CANCEL" | null>(null);
  const checkpointRef = useRef<Checkpoint | undefined>(undefined);
  const sessionIdRef = useRef("");
  const [order, setOrder] = useState<BlockId[]>(blocks.map(block => block.id));
  const [enabled, setEnabled] = useState<Record<BlockId, boolean>>(() =>
    Object.fromEntries(blocks.map(block => [block.id, true])) as Record<BlockId, boolean>);
  const [selected, setSelected] = useState<Record<Key, string[]>>(() => Object.fromEntries(
    blocks.flatMap(block => block.parameters.map(parameter => [parameter.key, [getValue(settings, parameter.key)]])),
  ) as Record<Key, string[]>);
  useEffect(() => { if (!asset && assets.length) setAsset(assets[0]); }, [asset, assets]);
  useEffect(() => {
    void api<OptimizationSession | null>("/api/v1/backtest/optimizations/active").then(session => {
      if (!session) return;
      const config = session.configuration;
      setOptimizationMode(config.optimizationMode); setMetric(config.metric); setAsset(config.asset);
      setTimeframes(config.timeframes); setOptimizationPeriod(config.optimizationPeriod);
      setValidationPeriod(config.validationPeriod); setValidationCount(Math.max(3, config.validationCount));
      setMinimumTrades(config.minimumTrades); setMinimumReturn(config.minimumReturn);
      setMaximumDrawdown(config.maximumDrawdown); setOrder(config.order); setEnabled(config.enabled);
      setSelected(config.selected); setRows(session.checkpoint.finalists.length ? session.checkpoint.finalists : session.checkpoint.completed);
      setTimings(session.checkpoint.timings ?? {});
      setSavedSession(session);
    }).catch(() => undefined);
  }, []);
  const active = order.map(id => blockMap.get(id)!).filter(block => enabled[block.id]);
  const counts = useMemo(() => active.map(block => block.id !== "entry"
    ? product(block.parameters.map(parameter => selected[parameter.key])).length
    : selected.entryModel.reduce((sum, model) => {
      const parameters = parametersForEntryModel(block, model as ElliottSettings["entryModel"]);
      return sum + product(parameters.filter(parameter => parameter.key !== "entryModel")
        .map(parameter => selected[parameter.key])).length;
    }, 0)), [active, selected]);
  const cascadeRunCount = counts.reduce((sum, count) => sum + count, 0);
  const exactGraphRunCount = counts.reduce((total, count) => total * count, 1);
  const naiveFullRunCount = active.reduce((total, block) => total * product(
    block.parameters.map(parameter => selected[parameter.key]),
  ).length, 1);
  const runCount = optimizationMode === "EXACT_GRAPH" ? exactGraphRunCount : cascadeRunCount;
  const blockEstimateSeconds = optimizationMode === "EXACT_GRAPH"
    ? estimatedFromTiming(exactGraphRunCount, timings.EXACT_GRAPH)
    : counts.reduce((sum, count, index) => sum + estimatedFromTiming(count, timings[active[index]?.id]), 0);
  const validationRuns = Math.min(validationCount, optimizationMode === "EXACT_GRAPH" ? exactGraphRunCount : counts.at(-1) ?? 0);
  const validationEstimateSeconds = estimatedFromTiming(validationRuns, timings.VALIDATION, false);
  const totalEstimateSeconds = blockEstimateSeconds + validationEstimateSeconds;
  const periodsValid = Date.parse(optimizationPeriod.from) <= Date.parse(optimizationPeriod.to)
    && Date.parse(optimizationPeriod.to) < Date.parse(validationPeriod.from)
    && Date.parse(validationPeriod.from) <= Date.parse(validationPeriod.to);
  const ranked = [...rows].sort((a, b) =>
    ((b.passed ? 2 : b.passed === false ? 1 : 0) - (a.passed ? 2 : a.passed === false ? 1 : 0))
    || ((b.score ?? b.optimizationScore) - (a.score ?? a.optimizationScore)));
  const best = ranked.find(row => row.passed);
  const makeCandidatesForParameters = (base: BacktestSettings, parameters: Parameter[], fixedModel?: string): Candidate[] =>
    product(parameters.filter(parameter => parameter.key !== "entryModel").map(parameter => selected[parameter.key])).map(values => {
    const varied = parameters.filter(parameter => parameter.key !== "entryModel");
    let next = base; values.forEach((value, index) => { next = setValue(next, varied[index].key, value); });
    if (fixedModel) next = setValue(next, "entryModel", fixedModel);
    if (!next.elliott.useMargin) next = { ...next, leverage: 1 };
    return {
      settings: next,
      label: [fixedModel ? `Модель входа: ${fixedModel}` : "", ...varied.map((parameter, index) => `${parameter.label}: ${values[index]}`)]
        .filter(Boolean).join(" · "),
    };
  }).filter(candidate => valid(candidate.settings));
  const makeCandidates = (base: BacktestSettings, block: Block): Candidate[] => block.id === "entry"
    ? selected.entryModel.flatMap(model => makeCandidatesForParameters(
      base, parametersForEntryModel(block, model as ElliottSettings["entryModel"]), model,
    ))
    : product(block.parameters.map(parameter => selected[parameter.key])).map(values => {
      let next = base; values.forEach((value, index) => { next = setValue(next, block.parameters[index].key, value); });
      if (!next.elliott.useMargin) next = { ...next, leverage: 1 };
      return { settings: next, label: block.parameters.map((parameter, index) => `${parameter.label}: ${values[index]}`).join(" · ") };
    }).filter(candidate => valid(candidate.settings));
  const uniqueCandidates = (candidates: Candidate[]) => [...new Map(candidates.map(candidate => [
    JSON.stringify(candidate.settings), candidate,
  ])).values()];
  const buildExactGraph = (initialSettings: BacktestSettings) => active.reduce<Candidate[]>((frontier, block) => uniqueCandidates(
    frontier.flatMap(parent => makeCandidates(parent.settings, block).map(child => ({
      ...child, label: [parent.label, child.label].filter(Boolean).join(" · "),
    }))),
  ), [{ settings: initialSettings, label: "" }]);
  const configuration = (): OptimizationConfiguration => ({ optimizationMode, metric, asset, timeframes, optimizationPeriod,
    validationPeriod, validationCount, minimumTrades, minimumReturn, maximumDrawdown, order, enabled, selected, settings });
  const persist = async (sessionId: string, status: "RUNNING" | "PAUSED" | "CANCELLED" | "COMPLETED" | "FAILED", checkpoint: Checkpoint, message?: string) => {
    await api(`/api/v1/backtest/optimizations/${sessionId}`, {
      method: "PUT", body: JSON.stringify({ status, checkpoint: checkpointForStorage(checkpoint), error: message }),
    });
    setLastSavedAt(new Date().toISOString());
  };
  const addTiming = (key: string, elapsedMs: number, runs = 1) => {
    const current = checkpointRef.current?.timings?.[key] ?? { runs: 0, elapsedMs: 0 };
    const next = { runs: current.runs + runs, elapsedMs: current.elapsedMs + elapsedMs };
    const all = { ...(checkpointRef.current?.timings ?? {}), [key]: next };
    if (checkpointRef.current) checkpointRef.current = { ...checkpointRef.current, timings: all };
    setTimings(all);
    return all;
  };
  const saveStage = async () => {
    if (!sessionIdRef.current || !checkpointRef.current) return;
    try { await persist(sessionIdRef.current, running ? "RUNNING" : "PAUSED", checkpointRef.current); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const processControl = async (sessionId: string, checkpoint: Checkpoint) => {
    const action = controlRequested.current;
    if (!action) return false;
    const status = action === "CANCEL" ? "CANCELLED" : "PAUSED";
    await persist(sessionId, status, checkpoint);
    controlRequested.current = null;
    if (status === "CANCELLED") { setSavedSession(null); setStage("Отменён"); }
    else setSavedSession({
      ...savedSession!, id: sessionId, status, configuration: configuration(), checkpoint, updated_at: new Date().toISOString(),
    });
    return true;
  };
  const saveTopConfigurations = async (sessionId: string, finalists: Row[]) => {
    const top = [...finalists].filter(row => row.validation).sort((a, b) =>
      ((b.passed ? 1 : 0) - (a.passed ? 1 : 0)) || ((b.score ?? -Infinity) - (a.score ?? -Infinity)),
    ).slice(0, 3);
    const library = await api<{ configurations: Array<{ id: string; name: string }> }>(
      "/api/v1/execution/configuration-library",
    );
    for (let index = 0; index < top.length; index += 1) {
      const row = top[index]; const name = `Оптимизация ${asset} · топ ${index + 1} · ${sessionId.slice(0, 8)}`;
      const existing = library.configurations.find(item => item.name === name);
      const validation = row.validation!;
      await api(`/api/v1/execution/configuration-library${existing ? `/${existing.id}` : ""}`, {
        method: existing ? "PUT" : "POST",
        body: JSON.stringify({
          name,
          description: `Автоматически сохранено после валидации. Доходность ${validation.totalReturnPercent.toFixed(2)}%, `
            + `просадка ${validation.maxDrawdownPercent.toFixed(2)}%, сделок ${validation.totalTrades}.`,
          config: row.settings,
        }),
      });
    }
    setSavedTopCount(top.length);
  };
  const run = async (resume = false) => {
    if (!active.length || !periodsValid) return;
    setRunning(true); setError(""); setSavedTopCount(0); controlRequested.current = null;
    let checkpoint: Checkpoint = resume && savedSession ? savedSession.checkpoint
      : { phase: "OPTIMIZATION", blockIndex: 0, offset: 0, completed: [], finalists: [], validationIndex: 0, timings: {} };
    // Persisted results intentionally contain metrics only. Re-run the small
    // finalist set after a resumed validation to restore report/chart details.
    if (resume && checkpoint.phase === "VALIDATION") checkpoint = { ...checkpoint, validationIndex: 0 };
    let sessionId = savedSession?.id ?? "";
    checkpointRef.current = checkpoint; sessionIdRef.current = sessionId; setTimings(checkpoint.timings ?? {});
    try {
      if (!resume || !savedSession) {
        setRows([]);
        const created = await api<OptimizationSession>("/api/v1/backtest/optimizations", {
          method: "POST", body: JSON.stringify({ configuration: configuration(), checkpoint }),
        });
        sessionId = created.id; sessionIdRef.current = sessionId; setSavedSession(created);
      } else {
        await persist(sessionId, "RUNNING", checkpoint);
      }
      let finalists: Row[] = checkpoint.finalists;
      if (optimizationMode === "EXACT_GRAPH") {
        const candidates = buildExactGraph(resume && savedSession ? savedSession.configuration.settings : settings);
        if (!candidates.length) throw new Error("В точном графе нет допустимых комбинаций.");
        setStage("Точный граф"); setTotal(candidates.length); const completed: Row[] = checkpoint.completed;
        for (let offset = checkpoint.offset; checkpoint.phase === "OPTIMIZATION" && offset < candidates.length; offset += PARALLEL_BATCH_SIZE) {
          const batch = candidates.slice(offset, offset + PARALLEL_BATCH_SIZE);
          const batchResults = await Promise.all(batch.map(async candidate => {
            const started = performance.now();
            const result = await runCandidate(candidate.settings, optimizationPeriod, asset, timeframes, true);
            return { row: { ...candidate, optimization: result, optimizationScore: score(result, metric) }, elapsedMs: performance.now() - started };
          }));
          completed.push(...batchResults.map(item => item.row));
          setDone(completed.length); setRows([...completed]);
          checkpoint = { ...checkpoint, offset: offset + batch.length, completed: [...completed],
            timings: addTiming("EXACT_GRAPH", batchResults.reduce((sum, item) => sum + item.elapsedMs, 0), batchResults.length) };
          checkpointRef.current = checkpoint; await persist(sessionId, "RUNNING", checkpoint);
          if (await processControl(sessionId, checkpoint)) return;
        }
        if (checkpoint.phase === "OPTIMIZATION") {
          completed.sort((a, b) => b.optimizationScore - a.optimizationScore);
          finalists = completed.slice(0, Math.min(validationCount, completed.length));
          checkpoint = { ...checkpoint, phase: "VALIDATION", finalists, completed: [], offset: 0, validationIndex: 0 };
          checkpointRef.current = checkpoint;
          await persist(sessionId, "RUNNING", checkpoint);
        }
      } else {
        let base = checkpoint.base ?? (resume && savedSession ? savedSession.configuration.settings : settings);
        for (let blockIndex = checkpoint.blockIndex ?? 0; checkpoint.phase === "OPTIMIZATION" && blockIndex < active.length; blockIndex += 1) {
          const block = active[blockIndex]; const candidates = makeCandidates(base, block);
          if (!candidates.length) throw new Error(`В блоке «${block.title}» нет допустимых комбинаций.`);
          setStage(`${blockIndex + 1}/${active.length}: ${block.title}`); setTotal(candidates.length); const completed: Row[] = checkpoint.completed;
          setDone(completed.length);
          for (let offset = checkpoint.offset; offset < candidates.length; offset += PARALLEL_BATCH_SIZE) {
            const batch = candidates.slice(offset, offset + PARALLEL_BATCH_SIZE);
            const batchResults = await Promise.all(batch.map(async candidate => {
              const started = performance.now();
              const result = await runCandidate(candidate.settings, optimizationPeriod, asset, timeframes, true);
              return {
                row: { ...candidate, optimization: result, optimizationScore: score(result, metric) },
                elapsedMs: performance.now() - started,
              };
            }));
            completed.push(...batchResults.map(item => item.row)); setDone(completed.length); setRows([...completed]);
            checkpoint = { ...checkpoint, blockIndex, offset: offset + batch.length, base, completed: [...completed],
              timings: addTiming(block.id, batchResults.reduce((sum, item) => sum + item.elapsedMs, 0), batchResults.length) };
            checkpointRef.current = checkpoint; await persist(sessionId, "RUNNING", checkpoint);
            if (await processControl(sessionId, checkpoint)) return;
          }
          completed.sort((a, b) => b.optimizationScore - a.optimizationScore); base = completed[0].settings; finalists = completed;
          checkpoint = { ...checkpoint, blockIndex: blockIndex + 1, offset: 0, base, completed: [], finalists };
          checkpointRef.current = checkpoint;
          await persist(sessionId, "RUNNING", checkpoint);
        }
        if (checkpoint.phase === "OPTIMIZATION") {
          finalists = finalists.slice(0, Math.min(validationCount, finalists.length));
          checkpoint = { ...checkpoint, phase: "VALIDATION", finalists, completed: [], offset: 0, validationIndex: 0 };
          checkpointRef.current = checkpoint;
          await persist(sessionId, "RUNNING", checkpoint);
        }
      }
      finalists = checkpoint.finalists.filter(row => valid(row.settings));
      if (!finalists.length) throw new Error("Сохранённые финалисты не соответствуют текущим ограничениям параметров.");
      if (finalists.length !== checkpoint.finalists.length) {
        checkpoint = { ...checkpoint, finalists, validationIndex: Math.min(checkpoint.validationIndex, finalists.length) };
        checkpointRef.current = checkpoint;
        await persist(sessionId, "RUNNING", checkpoint);
      }
      setRows([...finalists]); setStage("Валидация"); setDone(checkpoint.validationIndex); setTotal(finalists.length);
      for (let index = checkpoint.validationIndex; index < finalists.length; index += 1) {
        const candidate = finalists[index];
        const started = performance.now();
        candidate.validation = await runCandidate(candidate.settings, validationPeriod, asset, timeframes);
        candidate.score = Math.min(candidate.optimizationScore, score(candidate.validation, metric));
        candidate.passed = candidate.validation.totalTrades >= minimumTrades
          && candidate.validation.totalReturnPercent >= minimumReturn
          && candidate.validation.maxDrawdownPercent <= maximumDrawdown;
        setRows([...finalists]); setDone(index + 1);
        checkpoint = { ...checkpoint, finalists: [...finalists], validationIndex: index + 1,
          timings: addTiming("VALIDATION", performance.now() - started) };
        checkpointRef.current = checkpoint; await persist(sessionId, "RUNNING", checkpoint);
        if (await processControl(sessionId, checkpoint)) return;
      }
      await saveTopConfigurations(sessionId, finalists);
      await persist(sessionId, "COMPLETED", checkpoint); setSavedSession(null);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : String(reason); setError(message);
      if (sessionId) {
        await persist(sessionId, "PAUSED", checkpoint, message).catch(() => undefined);
        setSavedSession({ id: sessionId, status: "PAUSED", configuration: configuration(), checkpoint,
          updated_at: new Date().toISOString(), error: message });
      }
    } finally { setRunning(false); }
  };
  const move = (index: number, offset: number) => setOrder(current => {
    const next = [...current];
    [next[index], next[index + offset]] = [next[index + offset], next[index]];
    return next;
  });
  const dateField = (label: string, period: Period, key: keyof Period, update: (period: Period) => void) => <TextField type="date" label={label} value={period[key]} onChange={event => update({ ...period, [key]: event.target.value })} slotProps={{ inputLabel: { shrink: true } }} />;
  return <Stack spacing={2}><Paper variant="outlined" sx={{ p: 3 }}>
    <Typography variant="h5">Каскадный перебор параметров Elliott</Typography>
    <Alert severity="info" sx={{ my: 2 }}>Блоки выполняются сверху вниз. Победитель ступени передаётся в следующую, поэтому число прогонов складывается по блокам, а не перемножается. Внутри блока комбинации запускаются параллельными пакетами по {PARALLEL_BATCH_SIZE}.</Alert>
    <Alert severity="warning" sx={{ mb: 2 }}>Комиссии, проскальзывание, funding, задержка, ликвидность и биржевые шаги не перебираются и берутся из основной формы. Структурный Stop Loss, Risk/Reward и риск участвуют.</Alert>
    <TextField select fullWidth label="Режим оптимизации" value={optimizationMode}
      disabled={running} sx={{ mb: 2 }} onChange={event => setOptimizationMode(event.target.value as OptimizationMode)}>
      <MenuItem value="CASCADE">Быстрая лесенка — лучший результат каждой ступени</MenuItem>
      <MenuItem value="EXACT_GRAPH">Точный граф — все уникальные комбинации</MenuItem>
    </TextField>
    {optimizationMode === "EXACT_GRAPH" && <Alert severity="success" sx={{ mb: 2 }}>
      Точный граф сохраняет взаимодействия между блоками и не отбрасывает потенциальный глобальный максимум.
      Эквивалентные ветви параметров выбранных моделей входа объединяются.
    </Alert>}
    <Paper variant="outlined" sx={{ p: 2, mb: 2 }}><Stack spacing={1.5}><TextField select label="Актив" value={asset} onChange={event => setAsset(event.target.value)}>{assets.map(item => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><Stack><Typography variant="caption">Загружаемые таймфреймы</Typography><FormGroup row>{["M1", "M5", "M15", "M30", "H1", "H4", "D1"].map(item => <FormControlLabel key={item} label={item} control={<Checkbox checked={timeframes.includes(item)} disabled={timeframes.length === 1 && timeframes.includes(item)} onChange={event => setTimeframes(current => event.target.checked ? [...current, item] : current.filter(value => value !== item))} />} />)}</FormGroup></Stack></Stack></Paper>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>{dateField("Перебор: с", optimizationPeriod, "from", setOptimizationPeriod)}{dateField("Перебор: по", optimizationPeriod, "to", setOptimizationPeriod)}{dateField("Валидация: с", validationPeriod, "from", setValidationPeriod)}{dateField("Валидация: по", validationPeriod, "to", setValidationPeriod)}</Stack>
    {!periodsValid && <Alert severity="error" sx={{ mt: 1.5 }}>Периоды должны идти последовательно и не пересекаться.</Alert>}
    <Typography variant="h6" sx={{ mt: 2.5 }}>Порядок ступеней</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>Не отмеченные параметры блока фиксируются значениями основной формы.</Typography>
    <Stack spacing={1.5}>{order.map((id, index) => { const block = blockMap.get(id)!; const activeIndex = active.findIndex(item => item.id === id); return <Paper key={id} variant="outlined" sx={{ p: 2, opacity: enabled[id] ? 1 : .6 }}><Stack spacing={1.5}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1} sx={{ alignItems: { md: "center" } }}><FormControlLabel sx={{ flex: 1, m: 0 }} control={<Checkbox checked={enabled[id]} onChange={event => setEnabled({ ...enabled, [id]: event.target.checked })} />} label={`${index + 1}. ${block.title}`} /><Button size="small" disabled={index === 0 || running} onClick={() => move(index, -1)}>↑ Выше</Button><Button size="small" disabled={index === order.length - 1 || running} onClick={() => move(index, 1)}>↓ Ниже</Button></Stack>
      <Typography variant="body2" color="text.secondary">{block.description}</Typography>
      {enabled[id] && <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ flexWrap: "wrap" }}>{block.parameters.map(parameter => <FormControl key={parameter.key} sx={{ minWidth: 220, flex: "1 1 220px" }}><InputLabel>{parameter.label}</InputLabel><Select multiple label={parameter.label} value={selected[parameter.key]} onChange={event => { const next = typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value; if (next.length) setSelected({ ...selected, [parameter.key]: next }); }} renderValue={items => items.join(", ")}>{[...new Set([...parameter.options, ...selected[parameter.key]])].map(option => <MenuItem key={option} value={option}><Checkbox checked={selected[parameter.key].includes(option)} /><ListItemText primary={option} /></MenuItem>)}</Select><FormHelperText>{selected[parameter.key].length} знач.</FormHelperText></FormControl>)}</Stack>}
      {enabled[id] && <Typography variant="caption">
        Комбинаций: {counts[activeIndex]} · пакетов по {PARALLEL_BATCH_SIZE}: {Math.ceil(counts[activeIndex] / PARALLEL_BATCH_SIZE)}
        {" · "}время: {formatDuration(estimatedFromTiming(counts[activeIndex], timings[id]))}
        {timings[id]?.runs ? ` · замер 1 прогона: ${(timings[id].elapsedMs / timings[id].runs / 1000).toFixed(2)} сек` : " · ожидается первый замер"}
      </Typography>}
    </Stack></Paper>; })}</Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 2 }}><TextField select fullWidth label="Критерий" value={metric} onChange={event => setMetric(event.target.value as Metric)}><MenuItem value="RETURN_DD">Доходность − просадка</MenuItem><MenuItem value="RETURN">Доходность</MenuItem><MenuItem value="PROFIT_FACTOR">Profit Factor</MenuItem></TextField><TextField fullWidth type="number" label="Финалистов на валидацию" value={validationCount} slotProps={{ htmlInput: { min: 3 } }} onChange={event => setValidationCount(Math.max(3, Number(event.target.value)))} /></Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 1.5 }}><TextField fullWidth type="number" label="Мин. сделок" value={minimumTrades} onChange={event => setMinimumTrades(Math.max(0, Number(event.target.value)))} /><TextField fullWidth type="number" label="Мин. доходность, %" value={minimumReturn} onChange={event => setMinimumReturn(Number(event.target.value))} /><TextField fullWidth type="number" label="Макс. просадка, %" value={maximumDrawdown} onChange={event => setMaximumDrawdown(Math.max(0, Number(event.target.value)))} /></Stack>
    <Paper variant="outlined" sx={{ mt: 2, p: 2 }}><Stack spacing={.5}>
      <Typography variant="subtitle2">Предположительное время</Typography>
      <Typography variant="body2">До первого замера один прогон оценивается в ≈ {ESTIMATED_SEQUENTIAL_RUN_SECONDS} сек</Typography>
      {Object.entries(timings).map(([key, timing]) => <Typography variant="body2" key={key}>
        {key === "VALIDATION" ? "Валидация" : key === "EXACT_GRAPH" ? "Точный граф" : blockMap.get(key as BlockId)?.title ?? key}: {(timing.elapsedMs / timing.runs / 1000).toFixed(2)} сек/прогон ({timing.runs} замеров)
      </Typography>)}
      <Typography variant="body2">Лесенка: {cascadeRunCount.toLocaleString("ru-RU")} прогонов</Typography>
      <Typography variant="body2">Точный граф: до {exactGraphRunCount.toLocaleString("ru-RU")} уникальных прогонов</Typography>
      <Typography variant="body2">Полный перебор без графа: {naiveFullRunCount.toLocaleString("ru-RU")} прогонов</Typography>
      <Typography variant="body2">Выбранный режим: {formatDuration(blockEstimateSeconds)}</Typography>
      <Typography variant="body2">Валидация ({validationRuns} прогонов): {formatDuration(validationEstimateSeconds)}</Typography>
      <Typography sx={{ fontWeight: 700 }}>Общее время: {formatDuration(totalEstimateSeconds)}</Typography>
      <Typography variant="caption" color="text.secondary">После каждого пакета оценка автоматически пересчитывается по фактическим замерам.</Typography>
    </Stack></Paper>
    {savedSession && !running && <Alert severity="info" sx={{ mt: 2 }}>
      Найден сохранённый прогресс от {new Date(savedSession.updated_at).toLocaleString("ru-RU")}. Можно продолжить без повторного запуска завершённых комбинаций.
    </Alert>}
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 2 }}>
      {!running && <Button variant="contained" disabled={!asset || !timeframes.length || !active.length || !runCount || !periodsValid} onClick={() => void run(false)}>Запустить {runCount} прогонов + валидация</Button>}
      {savedSession && !running && <Button variant="contained" color="success" disabled={!periodsValid} onClick={() => void run(true)}>Возобновить сохранённый перебор</Button>}
      {running && <Button variant="outlined" color="warning" onClick={() => { controlRequested.current = "PAUSE"; }}>Пауза после пакета</Button>}
      {(running || savedSession) && <Button variant="outlined" onClick={() => void saveStage()}>Сохранить этап</Button>}
      {running && <Button variant="outlined" color="error" onClick={() => { controlRequested.current = "CANCEL"; }}>Отменить перебор</Button>}
      {running && <Typography sx={{ alignSelf: "center" }}>{stage}: {done} из {total}</Typography>}
    </Stack>
    {(running || savedSession) && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
      Автосохранение после каждого пакета{lastSavedAt ? ` · последнее: ${new Date(lastSavedAt).toLocaleTimeString("ru-RU")}` : ""}
    </Typography>}
    {running && <LinearProgress variant="determinate" value={total ? done / total * 100 : 0} sx={{ mt: 1.5 }} />}{error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
  </Paper>
  {!!rows.length && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h6">Топ-3 после валидации</Typography>{savedTopCount > 0 && <Alert severity="success" sx={{ mt: 1.5 }}>{savedTopCount} конфигурации сохранены в библиотеке конфигураций.</Alert>}{!best && !running && <Alert severity="warning" sx={{ mt: 1.5 }}>Финалисты не прошли условия валидации.</Alert>}{best && <><Typography sx={{ mt: 1 }}>{best.label}</Typography><Typography>Перебор: {best.optimization.totalReturnPercent.toFixed(2)}% · DD {best.optimization.maxDrawdownPercent.toFixed(2)}%</Typography><Typography>Валидация: {best.validation?.totalReturnPercent.toFixed(2)}% · DD {best.validation?.maxDrawdownPercent.toFixed(2)}%</Typography><Button variant="outlined" sx={{ mt: 1.5 }} onClick={() => onApply(best.settings, best.validation ?? best.optimization)}>Применить и открыть отчёт</Button></>}<Stack spacing={1} sx={{ mt: 2 }}>{ranked.filter(row => row.validation).slice(0, 3).map((row, index) => <Paper key={`${index}-${row.label}`} variant="outlined" sx={{ p: 1.5 }}><Typography>{index + 1}. {row.label}</Typography><Typography variant="caption">Перебор {row.optimization.totalReturnPercent.toFixed(2)}% · валидация {row.validation!.totalReturnPercent.toFixed(2)}% · DD {row.validation!.maxDrawdownPercent.toFixed(2)}% · {row.passed ? "прошёл" : "не прошёл"}</Typography><Button size="small" sx={{ mt: 1 }} onClick={() => onApply(row.settings, row.validation!)}>Применить</Button></Paper>)}</Stack></Paper>}
  </Stack>;
}
