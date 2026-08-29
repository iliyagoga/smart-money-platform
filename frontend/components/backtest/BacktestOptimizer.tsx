"use client";

import {
  Alert, Button, Checkbox, FormControl, FormControlLabel, FormGroup, FormHelperText, InputLabel, LinearProgress,
  ListItemText, MenuItem, Paper, Select, Stack, TextField, Typography,
} from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import type { BacktestResult, BacktestSettings, ElliottSettings } from "../../lib/backtest/types";

type Metric = "RETURN_DD" | "RETURN" | "PROFIT_FACTOR";
type Period = { from: string; to: string };
type Candidate = { settings: BacktestSettings; label: string };
type Row = Candidate & { optimization: BacktestResult; validation?: BacktestResult; optimizationScore: number; score?: number; passed?: boolean };

const values = (text: string) => [...new Set(text.split(",").map((value) => value.trim()).filter(Boolean))];
const rangeNumbers = (text: string, minimum: number, maximum: number, minimumExclusive = false) => values(text)
  .map(Number)
  .filter((value) => Number.isFinite(value) && (minimumExclusive ? value > minimum : value >= minimum) && value <= maximum);
const booleans = (text: string) => values(text).filter((value) => value === "true" || value === "false").map((value) => value === "true");
const product = <T,>(groups: T[][]): T[][] => groups.reduce<T[][]>(
  (rows, group) => rows.flatMap((row) => group.map((item) => [...row, item])), [[]],
);
const score = (result: BacktestResult, metric: Metric) => metric === "RETURN"
  ? result.totalReturnPercent
  : metric === "PROFIT_FACTOR" ? result.profitFactor ?? 0 : result.totalReturnPercent - result.maxDrawdownPercent;
const date = (timestamp: number) => new Date(timestamp).toISOString().slice(0, 10);
const defaultPeriods = (from: string, to: string) => {
  const start = Date.parse(`${from}T00:00:00Z`);
  const end = Date.parse(`${to}T00:00:00Z`);
  const split = start + Math.floor((end - start) * 0.7 / 86_400_000) * 86_400_000;
  return { optimization: { from, to: date(split) }, validation: { from: date(split + 86_400_000), to } };
};

interface Props {
  settings: BacktestSettings;
  assets: string[];
  initialAsset: string;
  initialTimeframes: string[];
  testFrom: string;
  testTo: string;
  onApply: (settings: BacktestSettings, result: BacktestResult) => void;
  runCandidate: (settings: BacktestSettings, period: Period, asset: string, timeframes: string[]) => Promise<BacktestResult>;
}

const availableTimeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const quarterSteps = (minimum: number, maximum: number) =>
  Array.from({ length: Math.round((maximum - minimum) / 0.25) + 1 }, (_, index) => minimum + index * 0.25);

export function BacktestOptimizer({
  settings, assets, initialAsset, initialTimeframes, testFrom, testTo, onApply, runCandidate,
}: Props) {
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
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState("Перебор");
  const [done, setDone] = useState(0);
  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const [architecture, setArchitecture] = useState({
    entryModels: String(settings.elliott.entryModel), zigzag: String(settings.elliott.zigzagReversalAtr),
    minSwing: String(settings.elliott.minSwingAtr), wave1Atr: String(settings.elliott.wave1MinAtr),
    efficiency: String(settings.elliott.wave1MinEfficiency), retracement: String(settings.elliott.entryRetracement),
    chochAtr: String(settings.elliott.chochMinAtr), minimumRr: String(settings.elliott.minimumRr),
  });
  const [capital, setCapital] = useState({
    initialCapital: String(settings.initialCapital), margin: String(settings.elliott.useMargin), leverage: String(settings.leverage),
    reinvest: String(settings.elliott.reinvestProfits), takeCount: String(settings.elliott.takeProfitCount),
    tp1: String(settings.elliott.takeProfitRr), tp2: String(settings.elliott.secondTakeProfitRr),
    actions: String(settings.elliott.firstTakeAction),
  });
  useEffect(() => {
    if (!asset && assets.length) setAsset(assets[0]);
  }, [asset, assets]);

  const candidates = useMemo<Candidate[]>(() => {
    const models = values(architecture.entryModels).filter((item): item is ElliottSettings["entryModel"] =>
      ["CHOCH_MARKET", "CHOCH_RETRACE", "WAVE1_BREAK_RETRACE"].includes(item));
    const architectureCandidates = product<string | number>([
      models, rangeNumbers(architecture.zigzag, 0.25, 10), rangeNumbers(architecture.minSwing, 0, 10),
      rangeNumbers(architecture.wave1Atr, 0, 20), rangeNumbers(architecture.efficiency, 0, 1),
      rangeNumbers(architecture.retracement, 0, 1), rangeNumbers(architecture.chochAtr, 0, 10),
      rangeNumbers(architecture.minimumRr, 0, 100, true),
    ]);
    const counts = rangeNumbers(capital.takeCount, 1, 2).filter((item): item is 1 | 2 => item === 1 || item === 2);
    const actions = values(capital.actions).filter((item): item is ElliottSettings["firstTakeAction"] =>
      ["PARTIAL_CLOSE", "MOVE_TO_BREAK_EVEN"].includes(item));
    const capitalCandidates = product<string | number | boolean>([
      rangeNumbers(capital.initialCapital, 0, 1_000_000_000, true), booleans(capital.margin),
      rangeNumbers(capital.leverage, 1, 100), booleans(capital.reinvest), counts,
      rangeNumbers(capital.tp1, 0, 100, true), rangeNumbers(capital.tp2, 0, 100, true), actions,
    ]);
    const generated = architectureCandidates.flatMap(
      ([entryModel, zigzag, minSwing, wave1Atr, efficiency, retracement, chochAtr, minimumRr]) =>
        capitalCandidates.flatMap(([initialCapital, useMargin, leverage, reinvest, takeCount, tp1, tp2, action]) => {
          const count = Number(takeCount) as 1 | 2;
          if (count === 2 && Number(tp2) <= Number(tp1)) return [];
          const actualLeverage = useMargin ? Number(leverage) : 1;
          return [{
            settings: { ...settings, initialCapital: Number(initialCapital), leverage: actualLeverage, elliott: {
              ...settings.elliott, entryModel: entryModel as ElliottSettings["entryModel"],
              zigzagReversalAtr: Number(zigzag), minSwingAtr: Number(minSwing), wave1MinAtr: Number(wave1Atr),
              wave1MinEfficiency: Number(efficiency), entryRetracement: Number(retracement), chochMinAtr: Number(chochAtr),
              minimumRr: Number(minimumRr), useMargin: Boolean(useMargin), reinvestProfits: Boolean(reinvest),
              takeProfitCount: count, takeProfitRr: Number(tp1), secondTakeProfitRr: Number(tp2),
              firstTakeAction: action as ElliottSettings["firstTakeAction"],
            } },
            label: `${entryModel} · ZZ ${zigzag} · W1 ${wave1Atr} · ${initialCapital} · ${useMargin ? `${actualLeverage}×` : "без маржи"} · TP ${tp1}${count === 2 ? `/${tp2}` : ""}`,
          }];
        }),
    );
    return [...new Map(generated.map((item) => [JSON.stringify(item.settings), item])).values()];
  }, [architecture, capital, settings]);

  const ranked = [...rows].sort((left, right) => {
    const validationRank = (row: Row) => row.passed === true ? 2 : row.passed === false ? 1 : 0;
    if (validationRank(left) !== validationRank(right)) return validationRank(right) - validationRank(left);
    return (right.score ?? right.optimizationScore) - (left.score ?? left.optimizationScore);
  });
  const best = ranked.find((row) => row.passed);
  const periodsValid = Date.parse(optimizationPeriod.from) <= Date.parse(optimizationPeriod.to)
    && Date.parse(optimizationPeriod.to) < Date.parse(validationPeriod.from)
    && Date.parse(validationPeriod.from) <= Date.parse(validationPeriod.to);

  const run = async () => {
    if (!candidates.length || !periodsValid) return;
    setRunning(true); setRows([]); setError(""); setStage("Перебор"); setDone(0); setTotal(candidates.length);
    try {
      const completed: Row[] = [];
      for (const candidate of candidates) {
        const result = await runCandidate(candidate.settings, optimizationPeriod, asset, timeframes);
        completed.push({ ...candidate, optimization: result, optimizationScore: score(result, metric) });
        setDone(completed.length);
      }
      completed.sort((left, right) => right.optimizationScore - left.optimizationScore);
      const finalists = completed.slice(0, Math.min(validationCount, completed.length));
      setRows([...completed]); setStage("Валидация"); setDone(0); setTotal(finalists.length);
      for (let index = 0; index < finalists.length; index += 1) {
        const candidate = finalists[index];
        candidate.validation = await runCandidate(candidate.settings, validationPeriod, asset, timeframes);
        candidate.score = Math.min(candidate.optimizationScore, score(candidate.validation, metric));
        candidate.passed = candidate.validation.totalTrades >= minimumTrades
          && candidate.validation.totalReturnPercent >= minimumReturn
          && candidate.validation.maxDrawdownPercent <= maximumDrawdown;
        setRows([...completed]); setDone(index + 1);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setRunning(false); }
  };

  const numberListField = (
    label: string, value: string, update: (value: string) => void, minimum: number, maximum: number, options: number[],
  ) => {
    const selected = rangeNumbers(value, minimum, maximum);
    const allOptions = [...new Set([...options, ...selected])].sort((left, right) => left - right);
    return <FormControl fullWidth>
      <InputLabel>{label}</InputLabel>
      <Select multiple label={label} value={selected} onChange={(event) => {
        const next = typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value;
        if (next.length) update(next.join(","));
      }} renderValue={(items) => items.join(", ")}>
        {allOptions.map((option) => <MenuItem key={option} value={option}>
          <Checkbox checked={selected.includes(option)} /><ListItemText primary={option} />
        </MenuItem>)}
      </Select>
      <FormHelperText>Допустимо: {minimum}–{maximum}</FormHelperText>
    </FormControl>;
  };
  const optionGroup = (
    title: string, selected: string, options: Array<{ value: string; label: string }>, update: (value: string) => void,
  ) => {
    const selectedValues = values(selected);
    return <Paper variant="outlined" sx={{ p: 1.5 }}>
      <Typography variant="subtitle2">{title}</Typography>
      <FormGroup row>{options.map((option) => <FormControlLabel key={option.value} label={option.label}
        control={<Checkbox checked={selectedValues.includes(option.value)}
          disabled={selectedValues.length === 1 && selectedValues.includes(option.value)}
          onChange={(event) => update(event.target.checked
            ? [...selectedValues, option.value].join(",")
            : selectedValues.filter((value) => value !== option.value).join(","))} />} />)}</FormGroup>
    </Paper>;
  };
  const dateField = (label: string, period: Period, key: keyof Period, update: (period: Period) => void) =>
    <TextField type="date" label={label} value={period[key]} onChange={(event) => update({ ...period, [key]: event.target.value })}
      slotProps={{ inputLabel: { shrink: true } }} />;

  return <Stack spacing={2}>
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5">Перебор параметров Elliott</Typography>
      <Alert severity="info" sx={{ my: 2 }}>
        Все комбинации сначала оцениваются на периоде перебора. Лучшие затем проверяются на независимом периоде валидации.
        Итоговый балл берётся по худшему из двух периодов.
      </Alert>
      <Paper variant="outlined" sx={{ p: 2, mb: 1.5 }}><Stack spacing={1.5}>
        <TextField select fullWidth label="Актив" value={asset} onChange={(event) => setAsset(event.target.value)}>
          {assets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>
        <Stack>
          <Typography variant="caption" color="text.secondary">Таймфреймы перебора</Typography>
          <FormGroup row>
            {availableTimeframes.map((item) => <FormControlLabel key={item} label={item} control={<Checkbox
              checked={timeframes.includes(item)}
              disabled={timeframes.length === 1 && timeframes.includes(item)}
              onChange={(event) => setTimeframes((current) => event.target.checked
                ? [...current, item]
                : current.filter((value) => value !== item))}
            />} />)}
          </FormGroup>
        </Stack>
      </Stack></Paper>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
        {dateField("Перебор: с", optimizationPeriod, "from", setOptimizationPeriod)}
        {dateField("Перебор: по", optimizationPeriod, "to", setOptimizationPeriod)}
        {dateField("Валидация: с", validationPeriod, "from", setValidationPeriod)}
        {dateField("Валидация: по", validationPeriod, "to", setValidationPeriod)}
      </Stack>
      {!periodsValid && <Alert severity="error" sx={{ mt: 1.5 }}>Периоды должны идти последовательно и не пересекаться.</Alert>}
      <Paper variant="outlined" sx={{ mt: 2, p: 2 }}><Stack spacing={2}>
        <Typography variant="h6">Единый набор параметров</Typography>
        <Typography variant="body2" color="text.secondary">
          Архитектура и капитал объединяются во все возможные комбинации. Числовые значения выбираются чекбоксами.
        </Typography>
        <Typography variant="subtitle1">Архитектура Elliott</Typography>
        {optionGroup("Модели входа", architecture.entryModels, [
          { value: "CHOCH_MARKET", label: "CHOCH market" }, { value: "CHOCH_RETRACE", label: "CHOCH retrace" },
          { value: "WAVE1_BREAK_RETRACE", label: "P1 break + retrace" },
        ], (value) => setArchitecture({ ...architecture, entryModels: value }))}
        <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
          <Typography variant="subtitle2">ATR ZigZag и первая волна</Typography>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {numberListField("Разворот ZigZag, ATR", architecture.zigzag,
              (value) => setArchitecture({ ...architecture, zigzag: value }), 0.25, 10, quarterSteps(0.25, 10))}
            {numberListField("Минимальный swing, ATR", architecture.minSwing,
              (value) => setArchitecture({ ...architecture, minSwing: value }), 0, 10, quarterSteps(0, 10))}
            {numberListField("Wave 1 минимум, ATR", architecture.wave1Atr,
              (value) => setArchitecture({ ...architecture, wave1Atr: value }), 0, 20, [0, 0.5, 1, 1.5, 2, 3, 5, 10, 20])}
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {numberListField("Wave 1 efficiency", architecture.efficiency,
              (value) => setArchitecture({ ...architecture, efficiency: value }), 0, 1, [0, 0.25, 0.35, 0.45, 0.5, 0.6, 0.75, 1])}
            {numberListField("Доля импульса от CHOCH (0 = ретест уровня)", architecture.retracement,
              (value) => setArchitecture({ ...architecture, retracement: value }), 0, 1, [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1])}
          </Stack>
        </Stack></Paper>
        <Paper variant="outlined" sx={{ p: 2 }}><Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          {numberListField("CHOCH displacement, ATR", architecture.chochAtr,
            (value) => setArchitecture({ ...architecture, chochAtr: value }), 0, 10, [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
          {numberListField("Минимальный RR", architecture.minimumRr,
            (value) => setArchitecture({ ...architecture, minimumRr: value }), 0.01, 100, [0.5, 1, 1.5, 2, 3, 4, 5, 8, 10, 20, 50, 100])}
        </Stack></Paper>
        <Typography variant="subtitle1">Капитал и управление</Typography>
        <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
          {numberListField("Начальный капитал", capital.initialCapital,
            (value) => setCapital({ ...capital, initialCapital: value }), 0.01, 1_000_000_000,
            [100, 500, 1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 1_000_000])}
          {optionGroup("Режим позиции", capital.margin, [
            { value: "false", label: "Без маржи" }, { value: "true", label: "С маржой" },
          ], (value) => setCapital({ ...capital, margin: value }))}
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {numberListField("Плечо", capital.leverage,
              (value) => setCapital({ ...capital, leverage: value }), 1, 100, [1, 2, 3, 5, 10, 20, 50, 100])}
            {optionGroup("Реинвестирование", capital.reinvest, [
              { value: "true", label: "Включено" }, { value: "false", label: "Выключено" },
            ], (value) => setCapital({ ...capital, reinvest: value }))}
          </Stack>
        </Stack></Paper>
        <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
          {optionGroup("Количество тейков", capital.takeCount, [
            { value: "1", label: "1 тейк" }, { value: "2", label: "2 тейка" },
          ], (value) => setCapital({ ...capital, takeCount: value }))}
          <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {numberListField("TP1, RR", capital.tp1, (value) => setCapital({ ...capital, tp1: value }),
              0.01, 100, [0.5, 1, 1.5, 2, 3, 4, 5, 8, 10, 20, 50, 100])}
            {numberListField("TP2, RR", capital.tp2, (value) => setCapital({ ...capital, tp2: value }),
              0.01, 100, [0.5, 1, 1.5, 2, 3, 4, 5, 8, 10, 20, 50, 100])}
          </Stack>
          {optionGroup("Действие при TP1", capital.actions, [
            { value: "PARTIAL_CLOSE", label: "Закрыть 50%" },
            { value: "MOVE_TO_BREAK_EVEN", label: "Перенести стоп в безубыток" },
          ], (value) => setCapital({ ...capital, actions: value }))}
        </Stack></Paper>
      </Stack></Paper>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 2 }}>
        <TextField select fullWidth label="Критерий результата" value={metric} onChange={(event) => setMetric(event.target.value as Metric)}>
          <MenuItem value="RETURN_DD">Доходность − просадка</MenuItem>
          <MenuItem value="RETURN">Максимальная доходность</MenuItem>
          <MenuItem value="PROFIT_FACTOR">Максимальный Profit Factor</MenuItem>
        </TextField>
        <TextField fullWidth type="number" label="Сколько лучших валидировать" value={validationCount}
          onChange={(event) => setValidationCount(Math.max(1, Number(event.target.value)))} />
      </Stack>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ mt: 1.5 }}>
        <TextField fullWidth type="number" label="Мин. сделок на валидации" value={minimumTrades}
          onChange={(event) => setMinimumTrades(Math.max(0, Number(event.target.value)))} />
        <TextField fullWidth type="number" label="Мин. доходность валидации, %" value={minimumReturn}
          onChange={(event) => setMinimumReturn(Number(event.target.value))} />
        <TextField fullWidth type="number" label="Макс. просадка валидации, %" value={maximumDrawdown}
          onChange={(event) => setMaximumDrawdown(Math.max(0, Number(event.target.value)))} />
      </Stack>
      <Button variant="contained"
        disabled={running || !asset || !timeframes.length || !candidates.length || !periodsValid}
        onClick={() => void run()} sx={{ mt: 2 }}>
        {running ? `${stage}: ${done} из ${total}` : `Запустить ${candidates.length} комбинаций`}
      </Button>
      {running && <LinearProgress variant="determinate" value={total ? done / total * 100 : 0} sx={{ mt: 1.5 }} />}
      {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
    </Paper>
    {!!rows.length && <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h6">Лучший подтверждённый результат</Typography>
      {!best && !running && <Alert severity="warning" sx={{ mt: 1.5 }}>
        Ни одна комбинация не прошла условия валидации. Лучший результат не выбран.
      </Alert>}
      {best && <>
        <Typography sx={{ mt: 1 }}>{best.label}</Typography>
        <Typography>Перебор: {best.optimization.totalReturnPercent.toFixed(2)}% · DD {best.optimization.maxDrawdownPercent.toFixed(2)}%</Typography>
        <Typography>Валидация: {best.validation?.totalReturnPercent.toFixed(2)}% · DD {best.validation?.maxDrawdownPercent.toFixed(2)}%</Typography>
        <Button variant="outlined" sx={{ mt: 1.5 }} onClick={() => onApply(best.settings, best.validation ?? best.optimization)}>
          Применить и открыть отчёт валидации
        </Button>
      </>}
      <Stack spacing={1} sx={{ mt: 2 }}>{ranked.slice(0, 10).map((row, index) =>
        <Paper key={`${index}-${row.label}`} variant="outlined" sx={{ p: 1.5 }}>
          <Typography>{index + 1}. {row.label}</Typography>
          <Typography variant="caption">
            Перебор {row.optimization.totalReturnPercent.toFixed(2)}%
            {row.validation ? ` · валидация ${row.validation.totalReturnPercent.toFixed(2)}% · ${row.passed ? "прошёл" : "не прошёл"}` : " · не валидирован"}
          </Typography>
        </Paper>)}</Stack>
    </Paper>}
  </Stack>;
}
