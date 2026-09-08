"use client";

import {
  Alert,
  Button,
  Checkbox,
  FormControl,
  FormHelperText,
  InputLabel,
  LinearProgress,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import {
  assessResult,
  DEFAULT_OPTIMIZATION_REQUIREMENTS,
  explorationValues,
  getOptimizerValue,
  isBetterEligibleResult,
  isGoodStageResult,
  meetsOptimizationRequirements,
  optimizationPeriod,
  OPTIMIZATION_PERIOD_SHARE,
  OPTIMIZER_PARAMETERS,
  parameterApplies,
  setOptimizerValue,
  validOptimizerSettings,
} from "../../lib/backtest/optimizer";
import type { OptimizationRequirements, OptimizerKey, ResultAssessment } from "../../lib/backtest/optimizer";
import type { BacktestResult, BacktestSettings } from "../../lib/backtest/types";

type Period = { from: string; to: string };
type TimeframeKey = "macroTimeframe" | "structureTimeframe" | "entryTimeframe";
type FinalResult = {
  settings: BacktestSettings;
  result: BacktestResult;
  assessment: ResultAssessment;
  acceptedChanges: string[];
  attempts: number;
  requirements: OptimizationRequirements;
  passedRequirements: boolean;
};

const timeframeOptions: Record<TimeframeKey, string[]> = {
  macroTimeframe: ["H1", "H4", "D1"],
  structureTimeframe: ["M15", "M30", "H1", "H4"],
  entryTimeframe: ["M1", "M5", "M15", "M30"],
};
const timeframeLabels: Record<TimeframeKey, string> = {
  macroTimeframe: "Macro TF",
  structureTimeframe: "Structure TF",
  entryTimeframe: "Entry TF",
};
const timeframeRank: Record<string, number> = {
  M1: 1, M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440,
};
const formatFactor = (value: number) => Number.isFinite(value) ? value.toFixed(2) : "∞";
const displayValue = (value: string) => value === "true" ? "вкл." : value === "false" ? "выкл." : value;

interface Props {
  settings: BacktestSettings;
  initialAsset: string;
  testFrom: string;
  testTo: string;
  onApply: (settings: BacktestSettings, result: BacktestResult) => void;
  runCandidate: (
    settings: BacktestSettings,
    period: Period,
    asset: string,
    timeframes: string[],
    persistResult?: boolean,
  ) => Promise<BacktestResult>;
}

export function BacktestOptimizer({
  settings,
  initialAsset,
  testFrom,
  testTo,
  onApply,
  runCandidate,
}: Props) {
  const [timeframes, setTimeframes] = useState<Record<TimeframeKey, string>>({
    macroTimeframe: settings.elliott.macroTimeframe,
    structureTimeframe: settings.elliott.structureTimeframe,
    entryTimeframe: settings.elliott.entryTimeframe,
  });
  const [excluded, setExcluded] = useState<OptimizerKey[]>([]);
  const [minimumTrades, setMinimumTrades] = useState(DEFAULT_OPTIMIZATION_REQUIREMENTS.minimumTrades);
  const [minimumProfitPercent, setMinimumProfitPercent] = useState(
    DEFAULT_OPTIMIZATION_REQUIREMENTS.minimumProfitPercent,
  );
  const [maximumLosingMonths, setMaximumLosingMonths] = useState(
    DEFAULT_OPTIMIZATION_REQUIREMENTS.maximumLosingMonths,
  );
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState("Ожидание запуска");
  const [completedStages, setCompletedStages] = useState(0);
  const [totalStages, setTotalStages] = useState(0);
  const [attempts, setAttempts] = useState(0);
  const [finalResult, setFinalResult] = useState<FinalResult>();
  const [error, setError] = useState("");

  const selectedSettings = useMemo(() => ({
    ...settings,
    elliott: { ...settings.elliott, ...timeframes },
  }), [settings, timeframes]);
  const selectedTimeframes = useMemo(() => [...new Set([
    timeframes.entryTimeframe,
    timeframes.structureTimeframe,
    timeframes.macroTimeframe,
  ])], [timeframes]);
  const timeframesValid = timeframeRank[timeframes.entryTimeframe] < timeframeRank[timeframes.structureTimeframe]
    && timeframeRank[timeframes.structureTimeframe] < timeframeRank[timeframes.macroTimeframe];
  const activeParameters = OPTIMIZER_PARAMETERS.filter((parameter) => !excluded.includes(parameter.key));
  const maximumRuns = 2 + activeParameters.reduce(
    (sum, parameter) => sum + explorationValues(parameter, selectedSettings).length,
    0,
  );
  const searchPeriod = optimizationPeriod(testFrom, testTo);
  const periodValid = Date.parse(`${searchPeriod.from}T00:00:00Z`) < Date.parse(`${searchPeriod.to}T23:59:59Z`)
    && Date.parse(`${searchPeriod.to}T23:59:59Z`) < Date.parse(`${testTo}T23:59:59Z`);

  const run = async () => {
    if (!initialAsset || !timeframesValid || !periodValid || !validOptimizerSettings(selectedSettings)) return;
    setRunning(true);
    setFinalResult(undefined);
    setError("");
    setAttempts(0);
    setCompletedStages(0);
    setTotalStages(activeParameters.length);
    const requirements: OptimizationRequirements = {
      minimumTrades,
      minimumProfitPercent,
      maximumLosingMonths,
    };
    try {
      let currentSettings = selectedSettings;
      let runCount = 0;
      const changes: string[] = [];
      setStage("Базовые значения обычного бэктеста");
      let currentResult = await runCandidate(currentSettings, searchPeriod, initialAsset, selectedTimeframes);
      runCount += 1;
      setAttempts(runCount);

      for (let parameterIndex = 0; parameterIndex < activeParameters.length; parameterIndex += 1) {
        const parameter = activeParameters[parameterIndex];
        setCompletedStages(parameterIndex);
        if (!parameterApplies(parameter, currentSettings)) continue;
        const baselineSettings = currentSettings;
        const baselineResult = currentResult;
        let stageSettings = baselineSettings;
        let stageResult = baselineResult;
        const values = explorationValues(parameter, baselineSettings);

        for (let valueIndex = 0; valueIndex < values.length; valueIndex += 1) {
          const value = values[valueIndex];
          const candidateSettings = setOptimizerValue(baselineSettings, parameter.key, value);
          if (!validOptimizerSettings(candidateSettings)) continue;
          setStage(`${parameterIndex + 1}/${activeParameters.length}: ${parameter.label} · ${displayValue(value)}`);
          const candidateResult = await runCandidate(
            candidateSettings,
            searchPeriod,
            initialAsset,
            selectedTimeframes,
          );
          runCount += 1;
          setAttempts(runCount);
          if (!meetsOptimizationRequirements(candidateResult, requirements)) continue;
          if (isBetterEligibleResult(candidateResult, stageResult, requirements)) {
            stageSettings = candidateSettings;
            stageResult = candidateResult;
          }
          if (isGoodStageResult(candidateResult, baselineResult, requirements)) {
            stageSettings = candidateSettings;
            stageResult = candidateResult;
            if (parameter.key !== "riskPerTradePercent" && parameter.key !== "leverage") break;
          }
        }

        if (isBetterEligibleResult(stageResult, baselineResult, requirements)) {
          changes.push(
            `${parameter.label}: ${displayValue(getOptimizerValue(baselineSettings, parameter.key))}`
            + ` → ${displayValue(getOptimizerValue(stageSettings, parameter.key))}`,
          );
          currentSettings = stageSettings;
          currentResult = stageResult;
        }
      }

      setCompletedStages(activeParameters.length);
      setStage("Итоговая валидация на всём периоде");
      const result = await runCandidate(
        currentSettings,
        { from: testFrom, to: testTo },
        initialAsset,
        selectedTimeframes,
        true,
      );
      runCount += 1;
      setAttempts(runCount);
      setFinalResult({
        settings: currentSettings,
        result,
        assessment: assessResult(result),
        acceptedChanges: changes,
        attempts: runCount,
        requirements,
        passedRequirements: meetsOptimizationRequirements(result, requirements),
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setRunning(false);
    }
  };

  return <Stack spacing={2}>
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h5">Последовательный перебор параметров Elliott</Typography>
      <Alert severity="info" sx={{ my: 2 }}>
        Поиск начинает с текущих значений обычного бэктеста. Для каждого параметра он проверяет значения
        сначала вниз от исходного, затем вверх. Сначала результат фильтруется по обязательным условиям;
        только после этого оценивается его кривая и остальные метрики. Модель входа проверяется первой.
        Перебор выполняется на первых {OPTIMIZATION_PERIOD_SHARE * 100}% периода, итоговая валидация — на всём периоде.
      </Alert>
      <Alert severity="warning" sx={{ mb: 2 }}>
        Комиссии, funding, проскальзывание, задержка и биржевые ограничения берутся из основной формы
        и не участвуют в переборе.
      </Alert>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Таймфреймы</Typography>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          {(Object.keys(timeframeOptions) as TimeframeKey[]).map((key) => <TextField
            key={key}
            select
            fullWidth
            disabled={running}
            label={timeframeLabels[key]}
            value={timeframes[key]}
            onChange={(event) => setTimeframes((current) => ({ ...current, [key]: event.target.value }))}
          >
            {timeframeOptions[key].map((option) => <MenuItem key={option} value={option}>{option}</MenuItem>)}
          </TextField>)}
        </Stack>
        {!timeframesValid && <Alert severity="error" sx={{ mt: 1.5 }}>
          Таймфреймы должны идти в порядке Entry &lt; Structure &lt; Macro.
        </Alert>}
      </Paper>

      <FormControl fullWidth disabled={running}>
        <InputLabel>Исключить из перебора</InputLabel>
        <Select
          multiple
          label="Исключить из перебора"
          value={excluded}
          onChange={(event) => setExcluded(
            (typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value) as OptimizerKey[],
          )}
          renderValue={(selected) => selected.length
            ? `${selected.length} параметров исключено`
            : "Ничего не исключено"}
        >
          {OPTIMIZER_PARAMETERS.map((parameter, index) => <MenuItem key={parameter.key} value={parameter.key}>
            <Checkbox checked={excluded.includes(parameter.key)} />
            <ListItemText primary={`${index + 1}. ${parameter.label}`} />
          </MenuItem>)}
        </Select>
        <FormHelperText>
          {activeParameters.length} из {OPTIMIZER_PARAMETERS.length} параметров участвуют в поиске
        </FormHelperText>
      </FormControl>

      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Обязательные условия результата</Typography>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <TextField
            fullWidth
            type="number"
            disabled={running}
            label="Минимум сделок"
            value={minimumTrades}
            slotProps={{ htmlInput: { min: 1, step: 1 } }}
            onChange={(event) => setMinimumTrades(Math.max(1, Math.floor(Number(event.target.value) || 1)))}
          />
          <TextField
            fullWidth
            type="number"
            disabled={running}
            label="Минимальная прибыль, %"
            value={minimumProfitPercent}
            slotProps={{ htmlInput: { step: .1 } }}
            onChange={(event) => setMinimumProfitPercent(Number(event.target.value) || 0)}
          />
          <TextField
            fullWidth
            type="number"
            disabled={running}
            label="Максимум убыточных месяцев"
            value={maximumLosingMonths}
            slotProps={{ htmlInput: { min: 0, step: 1 } }}
            onChange={(event) => setMaximumLosingMonths(Math.max(0, Math.floor(Number(event.target.value) || 0)))}
          />
        </Stack>
        <FormHelperText sx={{ mt: 1 }}>
          Вариант, который не проходит хотя бы одно условие, не считается хорошим даже при высокой оценке кривой.
        </FormHelperText>
      </Paper>

      <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle2">Как выбирается результат</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
          После обязательного фильтра главным критерием является итоговая прибыль. Затем оценивается
          equity-кривая. Время и капитал нормализуются, после чего для каждой точки считается
          перпендикулярное расстояние до прямой между началом и концом. Используется среднеквадратичное
          расстояние RMSE, поэтому крупные отклонения штрафуются сильнее. Score рассчитывается по
          гауссовой формуле 100 × exp(−0.5 × (RMSE / 0.1)²). Следом сравниваются убыточные месяцы,
          Profit Factor, Win Rate и Sharpe Ratio.
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
          Риск на сделку, режим без маржи/с маржой и размер плеча также перебираются автоматически.
          Риск и плечо перебираются от 1 до 5; плечо не может превышать риск. Для них проверяется весь
          диапазон, чтобы выбрать максимальную прибыль. Начальный капитал остаётся таким, как в основной
          форме. RR перебирается от 0.5 до 5 с шагом 0.5.
        </Typography>
        <Typography variant="body2" sx={{ mt: 1 }}>
          Перебор ({OPTIMIZATION_PERIOD_SHARE * 100}%): {searchPeriod.from}–{searchPeriod.to}.
          Итоговая валидация (100%): {testFrom}–{testTo}.
        </Typography>
        <Typography variant="body2">
          Максимум {maximumRuns.toLocaleString("ru-RU")} запусков; ранняя остановка обычно заметно сокращает их число.
        </Typography>
      </Paper>

      <Button
        variant="contained"
        sx={{ mt: 2 }}
        disabled={running || !initialAsset || !timeframesValid || !periodValid || !validOptimizerSettings(selectedSettings)}
        onClick={() => void run()}
      >
        {running ? `${stage} · запусков ${attempts}` : "Запустить автоматический перебор"}
      </Button>
      {running && <LinearProgress
        variant="determinate"
        value={totalStages ? completedStages / totalStages * 100 : 0}
        sx={{ mt: 1.5 }}
      />}
      {!periodValid && <Alert severity="error" sx={{ mt: 1.5 }}>
        Для автоматического разделения на перебор и итоговую проверку нужен период не короче двух дней.
      </Alert>}
      {error && <Alert severity="error" sx={{ mt: 1.5 }}>{error}</Alert>}
    </Paper>

    {finalResult && <Paper variant="outlined" sx={{ p: 3 }}>
      <Typography variant="h6">Итоговый вариант</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: .5 }}>
        Получен за {finalResult.attempts} запусков. Итоговые метрики валидированы на всём выбранном периоде.
      </Typography>
      <Alert severity={finalResult.passedRequirements ? "success" : "error"} sx={{ mt: 2 }}>
        {finalResult.passedRequirements
          ? "Итоговая оценка: хороший вариант — все обязательные условия выполнены."
          : "Итоговая оценка: условия не выполнены. Это лучший найденный вариант, но он не считается хорошим."}
      </Alert>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mt: 2, flexWrap: "wrap" }}>
        <Typography>
          Сделок: {finalResult.result.totalTrades} / минимум {finalResult.requirements.minimumTrades}
        </Typography>
        <Typography>
          Прибыль: {finalResult.result.netProfit.toFixed(2)} ({finalResult.result.totalReturnPercent.toFixed(2)}%)
          {` / минимум ${finalResult.requirements.minimumProfitPercent.toFixed(2)}%`}
        </Typography>
        <Typography>
          Кривая: {finalResult.assessment.curveScore.toFixed(1)}/100
          {` · отклонение ${finalResult.assessment.curveDeviationPercent.toFixed(1)}%`}
        </Typography>
        <Typography>Max DD: {finalResult.result.maxDrawdownPercent.toFixed(2)}%</Typography>
        <Typography>Profit Factor: {formatFactor(finalResult.assessment.profitFactor)}</Typography>
        <Typography>
          Убыточных месяцев: {finalResult.assessment.losingMonths} / максимум {finalResult.requirements.maximumLosingMonths}
        </Typography>
        <Typography>Win Rate: {finalResult.result.winRate.toFixed(1)}%</Typography>
        <Typography>Sharpe: {(finalResult.result.sharpeRatio ?? 0).toFixed(2)}</Typography>
      </Stack>
      {!!finalResult.acceptedChanges.length && <Paper variant="outlined" sx={{ p: 2, mt: 2 }}>
        <Typography variant="subtitle2">Принятые изменения</Typography>
        <Stack spacing={.5} sx={{ mt: 1 }}>
          {finalResult.acceptedChanges.map((change) => <Typography key={change} variant="body2">{change}</Typography>)}
        </Stack>
      </Paper>}
      {!finalResult.acceptedChanges.length && <Alert severity="info" sx={{ mt: 2 }}>
        Исходные значения основной формы оказались лучшим вариантом.
      </Alert>}
      <Button
        variant="outlined"
        sx={{ mt: 2 }}
        onClick={() => onApply(finalResult.settings, finalResult.result)}
      >
        Применить и открыть отчёт
      </Button>
    </Paper>}
  </Stack>;
}
