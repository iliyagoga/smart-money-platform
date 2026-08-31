"use client";

import { Alert, Button, Checkbox, FormControl, FormControlLabel, FormGroup, FormHelperText, InputLabel, LinearProgress, ListItemText, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import type { BacktestResult, BacktestSettings, ElliottSettings } from "../../lib/backtest/types";

type Metric = "RETURN_DD" | "RETURN" | "PROFIT_FACTOR";
type Period = { from: string; to: string };
type Candidate = { settings: BacktestSettings; label: string };
type Row = Candidate & { optimization: BacktestResult; validation?: BacktestResult; optimizationScore: number; score?: number; passed?: boolean };
type Key = "directionMode" | "macroTimeframe" | "structureTimeframe" | "entryTimeframe" | "atrPeriod" | "zigzagReversalAtr" | "minSwingAtr" | "wave1MinAtr" | "wave1MinEfficiency" | "wave2MinRetracement" | "wave2MaxRetracement" | "entryModel" | "entryRetracement" | "entryExpiryBars" | "chochMinAtr" | "chochMinBodyRatio" | "adxPeriod" | "adxMin" | "requireDiConfirmation" | "stopBufferAtr" | "minimumRr" | "takeProfitCount" | "takeProfitRr" | "secondTakeProfitRr" | "firstTakeAction" | "initialCapital" | "useMargin" | "leverage" | "reinvestProfits" | "riskPerTradePercent";
type BlockId = "context" | "wave" | "entry" | "protection" | "capital";
type Parameter = { key: Key; label: string; options: string[] };
type Block = { id: BlockId; title: string; description: string; parameters: Parameter[] };

const strings = (items: Array<string | number | boolean>) => items.map(String);
const quarter = (min: number, max: number) => strings(Array.from({ length: Math.round((max - min) / .25) + 1 }, (_, i) => min + i * .25));
const tenths = (min: number, max: number) => strings(Array.from(
  { length: Math.round((max - min) * 10) + 1 },
  (_, index) => Number((min + index / 10).toFixed(1)),
));
const product = <T,>(groups: T[][]): T[][] => groups.reduce<T[][]>((rows, group) => rows.flatMap(row => group.map(item => [...row, item])), [[]]);
const score = (result: BacktestResult, metric: Metric) => metric === "RETURN" ? result.totalReturnPercent : metric === "PROFIT_FACTOR" ? result.profitFactor ?? 0 : result.totalReturnPercent - result.maxDrawdownPercent;
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
    { key: "entryModel", label: "Модель входа", options: ["CHOCH_MARKET", "CHOCH_RETRACE", "WAVE1_BREAK_RETRACE"] },
    { key: "entryRetracement", label: "Доля импульса CHOCH", options: strings([0, .236, .382, .5, .618, .786, 1]) },
    { key: "entryExpiryBars", label: "Ждать вход, свечей", options: strings([1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100]) },
    { key: "chochMinAtr", label: "CHOCH displacement, ATR", options: strings([0, .25, .5, .75, 1, 1.5, 2, 3, 5, 10]) },
    { key: "chochMinBodyRatio", label: "Мин. тело свечи", options: strings([0, .25, .35, .5, .6, .75, 1]) },
    { key: "adxPeriod", label: "Период ADX", options: strings([7, 10, 14, 20, 21, 28, 50, 100]) },
    { key: "adxMin", label: "Минимальный ADX", options: strings([0, 10, 15, 20, 25, 30, 40, 50]) },
    { key: "requireDiConfirmation", label: "Подтверждение +DI/-DI", options: ["false", "true"] },
  ] },
  { id: "protection", title: "Stop Loss и Risk/Reward", description: "Структурный стоп, RR и управление тейками.", parameters: [
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
const ESTIMATED_BATCH_SECONDS = PARALLEL_BATCH_SIZE * ESTIMATED_SEQUENTIAL_RUN_SECONDS;
const estimatedBlockSeconds = (count: number) => Math.ceil(count / PARALLEL_BATCH_SIZE) * ESTIMATED_BATCH_SECONDS;
const formatDuration = (seconds: number) => {
  if (seconds < 60) return `≈ ${seconds} сек`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.ceil((seconds % 3600) / 60);
  if (hours) return `≈ ${hours} ч ${minutes} мин`;
  return `≈ ${minutes} мин`;
};
const rootKeys = new Set<Key>(["directionMode", "initialCapital", "leverage", "riskPerTradePercent"]);
const stringKeys = new Set<Key>(["directionMode", "macroTimeframe", "structureTimeframe", "entryTimeframe", "entryModel", "firstTakeAction"]);
const booleanKeys = new Set<Key>(["requireDiConfirmation", "useMargin", "reinvestProfits"]);
const getValue = (settings: BacktestSettings, key: Key) => String(rootKeys.has(key) ? settings[key as "initialCapital"] : settings.elliott[key as keyof ElliottSettings]);
function setValue(settings: BacktestSettings, key: Key, raw: string): BacktestSettings {
  const value: string | number | boolean = booleanKeys.has(key) ? raw === "true" : stringKeys.has(key) ? raw : Number(raw);
  if (rootKeys.has(key)) return { ...settings, [key]: value } as BacktestSettings;
  return { ...settings, elliott: { ...settings.elliott, [key]: value } as ElliottSettings };
}
function valid(settings: BacktestSettings) {
  const e = settings.elliott;
  return settings.initialCapital > 0 && settings.leverage >= 1 && settings.riskPerTradePercent >= 0
    && e.wave2MinRetracement < e.wave2MaxRetracement && e.takeProfitRr > 0
    && (e.takeProfitCount === 1 || e.secondTakeProfitRr > e.takeProfitRr);
}

interface Props {
  settings: BacktestSettings; assets: string[]; initialAsset: string; initialTimeframes: string[];
  testFrom: string; testTo: string;
  onApply: (settings: BacktestSettings, result: BacktestResult) => void;
  runCandidate: (settings: BacktestSettings, period: Period, asset: string, timeframes: string[]) => Promise<BacktestResult>;
}

export function BacktestOptimizer({ settings, assets, initialAsset, initialTimeframes, testFrom, testTo, onApply, runCandidate }: Props) {
  const defaults = defaultPeriods(testFrom, testTo);
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
  const [order, setOrder] = useState<BlockId[]>(blocks.map(block => block.id));
  const [enabled, setEnabled] = useState<Record<BlockId, boolean>>(() =>
    Object.fromEntries(blocks.map(block => [block.id, true])) as Record<BlockId, boolean>);
  const [selected, setSelected] = useState<Record<Key, string[]>>(() => Object.fromEntries(
    blocks.flatMap(block => block.parameters.map(parameter => [parameter.key, [getValue(settings, parameter.key)]])),
  ) as Record<Key, string[]>);
  useEffect(() => { if (!asset && assets.length) setAsset(assets[0]); }, [asset, assets]);
  const active = order.map(id => blockMap.get(id)!).filter(block => enabled[block.id]);
  const counts = useMemo(() => active.map(block =>
    product(block.parameters.map(parameter => selected[parameter.key])).length), [active, selected]);
  const runCount = counts.reduce((sum, count) => sum + count, 0);
  const blockEstimateSeconds = counts.reduce((sum, count) => sum + estimatedBlockSeconds(count), 0);
  const validationRuns = Math.min(validationCount, counts.at(-1) ?? 0);
  const validationEstimateSeconds = validationRuns * ESTIMATED_SEQUENTIAL_RUN_SECONDS;
  const totalEstimateSeconds = blockEstimateSeconds + validationEstimateSeconds;
  const periodsValid = Date.parse(optimizationPeriod.from) <= Date.parse(optimizationPeriod.to)
    && Date.parse(optimizationPeriod.to) < Date.parse(validationPeriod.from)
    && Date.parse(validationPeriod.from) <= Date.parse(validationPeriod.to);
  const ranked = [...rows].sort((a, b) =>
    ((b.passed ? 2 : b.passed === false ? 1 : 0) - (a.passed ? 2 : a.passed === false ? 1 : 0))
    || ((b.score ?? b.optimizationScore) - (a.score ?? a.optimizationScore)));
  const best = ranked.find(row => row.passed);
  const makeCandidates = (base: BacktestSettings, block: Block): Candidate[] =>
    product(block.parameters.map(parameter => selected[parameter.key])).map(values => {
    let next = base; values.forEach((value, index) => { next = setValue(next, block.parameters[index].key, value); });
    if (!next.elliott.useMargin) next = { ...next, leverage: 1 };
    return {
      settings: next,
      label: block.parameters.map((parameter, index) => `${parameter.label}: ${values[index]}`).join(" · "),
    };
  }).filter(candidate => valid(candidate.settings));
  const run = async () => {
    if (!active.length || !periodsValid) return; setRunning(true); setRows([]); setError("");
    try {
      let base = settings; let finalists: Row[] = [];
      for (let blockIndex = 0; blockIndex < active.length; blockIndex += 1) {
        const block = active[blockIndex]; const candidates = makeCandidates(base, block);
        if (!candidates.length) throw new Error(`В блоке «${block.title}» нет допустимых комбинаций.`);
        setStage(`${blockIndex + 1}/${active.length}: ${block.title}`); setDone(0); setTotal(candidates.length); const completed: Row[] = [];
        for (let offset = 0; offset < candidates.length; offset += PARALLEL_BATCH_SIZE) {
          const batch = candidates.slice(offset, offset + PARALLEL_BATCH_SIZE);
          const batchResults = await Promise.all(batch.map(async candidate => {
            const result = await runCandidate(candidate.settings, optimizationPeriod, asset, timeframes);
            return { ...candidate, optimization: result, optimizationScore: score(result, metric) };
          }));
          completed.push(...batchResults);
          setDone(completed.length);
        }
        completed.sort((a, b) => b.optimizationScore - a.optimizationScore); base = completed[0].settings; finalists = completed;
      }
      finalists = finalists.slice(0, Math.min(validationCount, finalists.length));
      setRows([...finalists]); setStage("Валидация"); setDone(0); setTotal(finalists.length);
      for (let index = 0; index < finalists.length; index += 1) {
        const candidate = finalists[index];
        candidate.validation = await runCandidate(candidate.settings, validationPeriod, asset, timeframes);
        candidate.score = Math.min(candidate.optimizationScore, score(candidate.validation, metric));
        candidate.passed = candidate.validation.totalTrades >= minimumTrades
          && candidate.validation.totalReturnPercent >= minimumReturn
          && candidate.validation.maxDrawdownPercent <= maximumDrawdown;
        setRows([...finalists]); setDone(index + 1);
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); } finally { setRunning(false); }
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
        {" · "}время: {formatDuration(estimatedBlockSeconds(counts[activeIndex]))}
      </Typography>}
    </Stack></Paper>; })}</Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 2 }}><TextField select fullWidth label="Критерий" value={metric} onChange={event => setMetric(event.target.value as Metric)}><MenuItem value="RETURN_DD">Доходность − просадка</MenuItem><MenuItem value="RETURN">Доходность</MenuItem><MenuItem value="PROFIT_FACTOR">Profit Factor</MenuItem></TextField><TextField fullWidth type="number" label="Финалистов на валидацию" value={validationCount} onChange={event => setValidationCount(Math.max(1, Number(event.target.value)))} /></Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 1.5 }}><TextField fullWidth type="number" label="Мин. сделок" value={minimumTrades} onChange={event => setMinimumTrades(Math.max(0, Number(event.target.value)))} /><TextField fullWidth type="number" label="Мин. доходность, %" value={minimumReturn} onChange={event => setMinimumReturn(Number(event.target.value))} /><TextField fullWidth type="number" label="Макс. просадка, %" value={maximumDrawdown} onChange={event => setMaximumDrawdown(Math.max(0, Number(event.target.value)))} /></Stack>
    <Paper variant="outlined" sx={{ mt: 2, p: 2 }}><Stack spacing={.5}>
      <Typography variant="subtitle2">Предположительное время</Typography>
      <Typography variant="body2">Один параллельный проход до {PARALLEL_BATCH_SIZE} прогонов: ≈ {ESTIMATED_BATCH_SECONDS} сек</Typography>
      <Typography variant="body2">Один последовательный прогон: ≈ {ESTIMATED_SEQUENTIAL_RUN_SECONDS} сек</Typography>
      <Typography variant="body2">Все блоки: {formatDuration(blockEstimateSeconds)}</Typography>
      <Typography variant="body2">Валидация ({validationRuns} прогонов): {formatDuration(validationEstimateSeconds)}</Typography>
      <Typography sx={{ fontWeight: 700 }}>Общее время: {formatDuration(totalEstimateSeconds)}</Typography>
      <Typography variant="caption" color="text.secondary">Оценка зависит от длины датасета и нагрузки на сервис.</Typography>
    </Stack></Paper>
    <Button variant="contained" sx={{ mt: 2 }} disabled={running || !asset || !timeframes.length || !active.length || !runCount || !periodsValid} onClick={() => void run()}>{running ? `${stage}: ${done} из ${total}` : `Запустить ${runCount} прогонов + валидация`}</Button>
    {running && <LinearProgress variant="determinate" value={total ? done / total * 100 : 0} sx={{ mt: 1.5 }} />}{error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
  </Paper>
  {!!rows.length && <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h6">Лучший подтверждённый результат</Typography>{!best && !running && <Alert severity="warning" sx={{ mt: 1.5 }}>Финалисты не прошли условия валидации.</Alert>}{best && <><Typography sx={{ mt: 1 }}>{best.label}</Typography><Typography>Перебор: {best.optimization.totalReturnPercent.toFixed(2)}% · DD {best.optimization.maxDrawdownPercent.toFixed(2)}%</Typography><Typography>Валидация: {best.validation?.totalReturnPercent.toFixed(2)}% · DD {best.validation?.maxDrawdownPercent.toFixed(2)}%</Typography><Button variant="outlined" sx={{ mt: 1.5 }} onClick={() => onApply(best.settings, best.validation ?? best.optimization)}>Применить и открыть отчёт</Button></>}<Stack spacing={1} sx={{ mt: 2 }}>{ranked.slice(0, 10).map((row, index) => <Paper key={`${index}-${row.label}`} variant="outlined" sx={{ p: 1.5 }}><Typography>{index + 1}. {row.label}</Typography><Typography variant="caption">Перебор {row.optimization.totalReturnPercent.toFixed(2)}%{row.validation ? ` · валидация ${row.validation.totalReturnPercent.toFixed(2)}% · ${row.passed ? "прошёл" : "не прошёл"}` : " · не валидирован"}</Typography></Paper>)}</Stack></Paper>}
  </Stack>;
}
