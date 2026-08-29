"use client";

import { Alert, Box, Button, Checkbox, FormControlLabel, FormGroup, Grid, Paper, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useRef, useState } from "react";
import { AssetManager } from "../../components/backtest/AssetManager";
import { BacktestReport } from "../../components/backtest/BacktestReport";
import { BacktestHistory } from "../../components/backtest/BacktestHistory";
import { BacktestOptimizer } from "../../components/backtest/BacktestOptimizer";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { HistoryLoader } from "../../components/backtest/HistoryLoader";
import { DatasetOverview } from "../../components/backtest/DatasetOverview";
import { SectionPage } from "../../components/layout/SectionPage";
import { api, downloadApi } from "../../lib/api";
import { useApiResource } from "../../hooks/useApiResource";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { mapBacktestResult } from "../../lib/backtest/apiTypes";
import type { BacktestCreateResponse, BacktestRun, BacktestRunsResponse, SavedBacktestRequest } from "../../lib/backtest/apiTypes";
import type { BacktestResult, BacktestSettings } from "../../lib/backtest/types";
import { useAuth } from "../../components/auth/AuthProvider";

const defaultSettings: BacktestSettings = {
  initialCapital: 10_000,
  strategy: "ELLIOTT",
  fastPeriod: 9,
  slowPeriod: 21,
  feePercent: 0.05,
  makerFeePercent: 0.02,
  takerFeePercent: 0.05,
  slippagePercent: 0.02,
  stopLossPercent: 2,
  takeProfitPercent: 4,
  positionSizePercent: 25,
  leverage: 1,
  fundingPercentPerDay: 0,
  fundingIntervalHours: 8,
  executionLatencyMs: 0,
  tickSize: 0.01,
  lotSize: 0.000001,
  minimumOrderSize: 0.000001,
  volumeParticipationPercent: 5,
  liquidationFeePercent: 0.5,
  trailingStopPercent: undefined,
  directionMode: "BOTH",
  riskPerTradePercent: 1,
  smcTargetMode: "TEMPLATE",
  smcTargetRr: 1.5,
  smcMinTargetRr: 1.5,
  smcMaxTargetRr: 8,
  kellyFraction: 0.25,
  confidenceThreshold: 0.5,
  templateIds: [],
  localRetraining: false,
  elliott: {
    useMargin: false,
    reinvestProfits: true,
    macroTimeframe: "H4", structureTimeframe: "H1", entryTimeframe: "M15", atrPeriod: 14,
    zigzagReversalAtr: 1.5, minSwingAtr: 1, wave1MinAtr: 1.5, wave1MinEfficiency: 0.45,
    wave2MinRetracement: 0.382, wave2MaxRetracement: 0.786, entryModel: "CHOCH_RETRACE",
    entryRetracement: 0.5, entryExpiryBars: 4, chochMinAtr: 0.5, chochMinBodyRatio: 0.5,
    macroFilter: "STRUCTURE", stopBufferAtr: 0.2, takeProfitCount: 2, takeProfitRr: 2, secondTakeProfitRr: 3,
    minimumRr: 1.5, breakEvenAtOneR: false, firstTakeAction: "PARTIAL_CLOSE",
  },
};

const timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
const timeframeMilliseconds: Record<string, number> = {
  M1: 60_000, M5: 300_000, M15: 900_000, M30: 1_800_000, H1: 3_600_000, H4: 14_400_000, D1: 86_400_000,
};

const savedNumber = (value: unknown, fallback: number) => typeof value === "number" ? value : fallback;
const savedBoolean = (value: unknown, fallback: boolean) => typeof value === "boolean" ? value : fallback;
const savedDate = (value: number) => new Date(value).toISOString().slice(0, 10);

function restoreSettings(request: SavedBacktestRequest, current: BacktestSettings): BacktestSettings {
  const config = request.config;
  const elliott = config.elliott ?? {};
  const fixedSmcTarget = typeof config.smc_target_rr === "number";
  return {
    ...current,
    initialCapital: savedNumber(config.initial_capital, current.initialCapital),
    strategy: typeof config.strategy === "string" ? config.strategy as BacktestSettings["strategy"] : current.strategy,
    fastPeriod: savedNumber(config.fast_period, current.fastPeriod),
    slowPeriod: savedNumber(config.slow_period, current.slowPeriod),
    feePercent: savedNumber(config.fee_percent, current.feePercent),
    makerFeePercent: savedNumber(config.maker_fee_percent, current.makerFeePercent ?? current.feePercent),
    takerFeePercent: savedNumber(config.taker_fee_percent, current.takerFeePercent ?? current.feePercent),
    slippagePercent: savedNumber(config.slippage_percent, current.slippagePercent),
    stopLossPercent: savedNumber(config.stop_loss_percent, current.stopLossPercent),
    takeProfitPercent: savedNumber(config.take_profit_percent, current.takeProfitPercent),
    positionSizePercent: savedNumber(config.position_size_percent, current.positionSizePercent),
    leverage: savedNumber(config.leverage, current.leverage),
    fundingPercentPerDay: savedNumber(config.funding_percent_per_day, current.fundingPercentPerDay),
    fundingIntervalHours: savedNumber(config.funding_interval_hours, current.fundingIntervalHours ?? 8),
    executionLatencyMs: savedNumber(config.execution_latency_ms, current.executionLatencyMs ?? 0),
    tickSize: savedNumber(config.tick_size, current.tickSize ?? .01),
    lotSize: savedNumber(config.lot_size, current.lotSize ?? .000001),
    minimumOrderSize: savedNumber(config.minimum_order_size, current.minimumOrderSize ?? .000001),
    volumeParticipationPercent: savedNumber(config.volume_participation_percent, current.volumeParticipationPercent ?? 5),
    liquidationFeePercent: savedNumber(config.liquidation_fee_percent, current.liquidationFeePercent ?? .5),
    trailingStopPercent: typeof config.trailing_stop_percent === "number" ? config.trailing_stop_percent : undefined,
    directionMode: typeof config.direction_mode === "string" ? config.direction_mode as BacktestSettings["directionMode"] : current.directionMode,
    riskPerTradePercent: savedNumber(config.risk_per_trade_percent, current.riskPerTradePercent),
    smcTargetMode: fixedSmcTarget ? "FIXED" : "TEMPLATE",
    smcTargetRr: savedNumber(config.smc_target_rr, current.smcTargetRr),
    smcMinTargetRr: savedNumber(config.smc_min_target_rr, current.smcMinTargetRr),
    smcMaxTargetRr: savedNumber(config.smc_max_target_rr, current.smcMaxTargetRr),
    kellyFraction: savedNumber(config.kelly_fraction, current.kellyFraction),
    confidenceThreshold: savedNumber(config.confidence_threshold, current.confidenceThreshold),
    templateIds: Array.isArray(config.template_ids) ? config.template_ids.filter((item): item is string => typeof item === "string") : current.templateIds,
    localRetraining: savedBoolean(config.local_retraining, current.localRetraining),
    elliott: {
      ...current.elliott,
      useMargin: savedBoolean(elliott.use_margin, current.elliott.useMargin),
      reinvestProfits: savedBoolean(elliott.reinvest_profits, current.elliott.reinvestProfits),
      macroTimeframe: typeof elliott.macro_timeframe === "string" ? elliott.macro_timeframe : current.elliott.macroTimeframe,
      structureTimeframe: typeof elliott.structure_timeframe === "string" ? elliott.structure_timeframe : current.elliott.structureTimeframe,
      entryTimeframe: typeof elliott.entry_timeframe === "string" ? elliott.entry_timeframe : current.elliott.entryTimeframe,
      atrPeriod: savedNumber(elliott.atr_period, current.elliott.atrPeriod),
      zigzagReversalAtr: savedNumber(elliott.zigzag_reversal_atr, current.elliott.zigzagReversalAtr),
      minSwingAtr: savedNumber(elliott.min_swing_atr, current.elliott.minSwingAtr),
      wave1MinAtr: savedNumber(elliott.wave1_min_atr, current.elliott.wave1MinAtr),
      wave1MinEfficiency: savedNumber(elliott.wave1_min_efficiency, current.elliott.wave1MinEfficiency),
      wave2MinRetracement: savedNumber(elliott.wave2_min_retracement, current.elliott.wave2MinRetracement),
      wave2MaxRetracement: savedNumber(elliott.wave2_max_retracement, current.elliott.wave2MaxRetracement),
      entryModel: typeof elliott.entry_model === "string" ? elliott.entry_model as BacktestSettings["elliott"]["entryModel"] : current.elliott.entryModel,
      entryRetracement: savedNumber(elliott.entry_retracement, current.elliott.entryRetracement),
      entryExpiryBars: savedNumber(elliott.entry_expiry_bars, current.elliott.entryExpiryBars),
      chochMinAtr: savedNumber(elliott.choch_min_atr, current.elliott.chochMinAtr),
      chochMinBodyRatio: savedNumber(elliott.choch_min_body_ratio, current.elliott.chochMinBodyRatio),
      macroFilter: typeof elliott.macro_filter === "string" ? elliott.macro_filter as BacktestSettings["elliott"]["macroFilter"] : current.elliott.macroFilter,
      stopBufferAtr: savedNumber(elliott.stop_buffer_atr, current.elliott.stopBufferAtr),
      takeProfitCount: savedNumber(elliott.take_profit_count, current.elliott.takeProfitCount) as 1 | 2,
      takeProfitRr: savedNumber(elliott.take_profit_rr, current.elliott.takeProfitRr),
      secondTakeProfitRr: savedNumber(elliott.second_take_profit_rr, current.elliott.secondTakeProfitRr),
      firstTakeAction: typeof elliott.first_take_action === "string" ? elliott.first_take_action as BacktestSettings["elliott"]["firstTakeAction"] : current.elliott.firstTakeAction,
      minimumRr: savedNumber(elliott.minimum_rr, current.elliott.minimumRr),
      breakEvenAtOneR: savedBoolean(elliott.break_even_at_one_r, current.elliott.breakEvenAtOneR),
    },
  };
}

interface ScenarioTemplatesResponse {
  templates: Array<{ id: string; name: string }>;
  total: number;
}

export default function BacktestPage() {
  const { roles } = useAuth();
  const [asset, setAsset] = useState("");
  const { addAsset, assetDetails, assets, reload: reloadAssets, removeAsset } = useTradingAssets();
  const [selectedTimeframes, setSelectedTimeframes] = useState(timeframes);
  const [candleLimit, setCandleLimit] = useState(10_000);
  const today = new Date().toISOString().slice(0, 10);
  const [trainFrom, setTrainFrom] = useState("2025-01-01");
  const [trainTo, setTrainTo] = useState("2025-06-30");
  const [testFrom, setTestFrom] = useState("2025-07-01");
  const [testTo, setTestTo] = useState(today);
  const [settings, setSettings] = useState(defaultSettings);
  const [result, setResult] = useState<BacktestResult>();
  const [comparison, setComparison] = useState<BacktestRun[]>([]);
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [workspaceTab, setWorkspaceTab] = useState(0);
  const [historyPage, setHistoryPage] = useState(0);
  const [historyRowsPerPage, setHistoryRowsPerPage] = useState(10);
  const [historyBusy, setHistoryBusy] = useState(false);
  const restoredConfig = useRef<SavedBacktestRequest["config"] | undefined>(undefined);
  const restoredModelVersion = useRef<string | null | undefined>(undefined);
  const runsResource = useApiResource<BacktestRunsResponse>(
    `/api/v1/backtest/backtests?limit=${historyRowsPerPage}&offset=${historyPage * historyRowsPerPage}`,
  );
  const templatesResource = useApiResource<ScenarioTemplatesResponse>("/api/v1/smc/scenario-templates");
  const templateSelectionInitialized = useRef(false);
  const templates = useMemo(() => templatesResource.data?.templates ?? [], [templatesResource.data?.templates]);
  useEffect(() => {
    const lastPage = Math.max(0, Math.ceil((runsResource.data?.total ?? 0) / historyRowsPerPage) - 1);
    if (historyPage > lastPage) setHistoryPage(lastPage);
  }, [historyPage, historyRowsPerPage, runsResource.data?.total]);
  useEffect(() => {
    if (templateSelectionInitialized.current || !templates.length) return;
    templateSelectionInitialized.current = true;
    setSettings((current) => current.templateIds.length
      ? current
      : { ...current, templateIds: templates.map((template) => template.id) });
  }, [templates]);
  const selectedAsset = asset || assets[0];
  const testRangeMilliseconds = Math.max(
    0,
    Date.parse(`${testTo}T23:59:59Z`) - Date.parse(`${testFrom}T00:00:00Z`),
  );
  const requiredTestCandleLimit = Math.min(2_000_000, Math.max(
    ...selectedTimeframes.map((item) => Math.ceil(testRangeMilliseconds / timeframeMilliseconds[item]) + 2),
  ));

  const executeBacktest = async (
    candidateSettings: BacktestSettings,
    period: { from: string; to: string },
    onProgress?: (value: number) => void,
    runAsset = selectedAsset,
    runTimeframes = selectedTimeframes,
    includeTrainingPeriod = true,
  ): Promise<BacktestResult> => {
    const periodMilliseconds = Math.max(
      0,
      Date.parse(`${period.to}T23:59:59Z`) - Date.parse(`${period.from}T00:00:00Z`),
    );
    const requiredCandleLimit = Math.min(2_000_000, Math.max(
      ...runTimeframes.map((item) => Math.ceil(periodMilliseconds / timeframeMilliseconds[item]) + 2),
    ));
    const effectiveCandleLimit = Math.max(candleLimit, requiredCandleLimit);
    if (effectiveCandleLimit !== candleLimit) setCandleLimit(effectiveCandleLimit);
    const runAssetDetails = assetDetails.find((item) => item.symbol === runAsset);
    try {
      const created = await api<BacktestCreateResponse>("/api/v1/backtest/backtests", {
        method: "POST",
        body: JSON.stringify({
          symbol: runAsset,
          timeframes: runTimeframes,
          candle_limit: effectiveCandleLimit,
          train_from: includeTrainingPeriod ? Date.parse(`${trainFrom}T00:00:00Z`) : undefined,
          train_to: includeTrainingPeriod ? Date.parse(`${trainTo}T23:59:59Z`) : undefined,
          test_from: Date.parse(`${period.from}T00:00:00Z`),
          test_to: Date.parse(`${period.to}T23:59:59Z`),
          model_version: restoredModelVersion.current,
          config: {
            ...restoredConfig.current,
            strategy: candidateSettings.strategy,
            initial_capital: candidateSettings.initialCapital,
            position_size_percent: candidateSettings.positionSizePercent,
            leverage: candidateSettings.leverage,
            fee_percent: candidateSettings.feePercent,
            maker_fee_percent: candidateSettings.makerFeePercent,
            taker_fee_percent: candidateSettings.takerFeePercent,
            slippage_percent: candidateSettings.slippagePercent,
            funding_percent_per_day: candidateSettings.fundingPercentPerDay,
            funding_interval_hours: candidateSettings.fundingIntervalHours,
            execution_latency_ms: candidateSettings.executionLatencyMs,
            tick_size: runAssetDetails?.tick_size ?? candidateSettings.tickSize,
            lot_size: runAssetDetails?.lot_size ?? candidateSettings.lotSize,
            minimum_order_size: runAssetDetails?.minimum_order_size ?? candidateSettings.minimumOrderSize,
            volume_participation_percent: candidateSettings.volumeParticipationPercent,
            liquidation_fee_percent: candidateSettings.liquidationFeePercent,
            stop_loss_percent: candidateSettings.stopLossPercent,
            take_profit_percent: candidateSettings.takeProfitPercent,
            trailing_stop_percent: candidateSettings.trailingStopPercent,
            fast_period: candidateSettings.fastPeriod,
            slow_period: candidateSettings.slowPeriod,
            direction_mode: candidateSettings.directionMode,
            risk_per_trade_percent: candidateSettings.riskPerTradePercent,
            smc_target_rr: candidateSettings.smcTargetMode === "FIXED" ? candidateSettings.smcTargetRr : undefined,
            smc_min_target_rr: candidateSettings.smcMinTargetRr,
            smc_max_target_rr: candidateSettings.smcMaxTargetRr,
            kelly_fraction: candidateSettings.kellyFraction,
            confidence_threshold: candidateSettings.confidenceThreshold,
            template_ids: candidateSettings.templateIds,
            local_retraining: candidateSettings.localRetraining,
            elliott: {
              ...(restoredConfig.current?.elliott ?? {}),
              use_margin: candidateSettings.elliott.useMargin,
              reinvest_profits: candidateSettings.elliott.reinvestProfits,
              macro_timeframe: candidateSettings.elliott.macroTimeframe,
              structure_timeframe: candidateSettings.elliott.structureTimeframe,
              entry_timeframe: candidateSettings.elliott.entryTimeframe,
              atr_period: candidateSettings.elliott.atrPeriod,
              zigzag_reversal_atr: candidateSettings.elliott.zigzagReversalAtr,
              min_swing_atr: candidateSettings.elliott.minSwingAtr,
              wave1_min_atr: candidateSettings.elliott.wave1MinAtr,
              wave1_min_efficiency: candidateSettings.elliott.wave1MinEfficiency,
              wave2_min_retracement: candidateSettings.elliott.wave2MinRetracement,
              wave2_max_retracement: candidateSettings.elliott.wave2MaxRetracement,
              entry_model: candidateSettings.elliott.entryModel,
              entry_retracement: candidateSettings.elliott.entryRetracement,
              entry_expiry_bars: candidateSettings.elliott.entryExpiryBars,
              choch_min_atr: candidateSettings.elliott.chochMinAtr,
              choch_min_body_ratio: candidateSettings.elliott.chochMinBodyRatio,
              macro_filter: candidateSettings.elliott.macroFilter,
              stop_buffer_atr: candidateSettings.elliott.stopBufferAtr,
              take_profit_count: candidateSettings.elliott.takeProfitCount,
              take_profit_rr: candidateSettings.elliott.takeProfitRr,
              second_take_profit_rr: candidateSettings.elliott.secondTakeProfitRr,
              first_take_action: candidateSettings.elliott.firstTakeAction,
              minimum_rr: candidateSettings.elliott.minimumRr,
              break_even_at_one_r: candidateSettings.elliott.breakEvenAtOneR,
            },
          },
        }),
      });
      let completed: BacktestRun | undefined;
      for (let attempt = 0; attempt < 3_600; attempt += 1) {
        const current = await api<BacktestRun>(`/api/v1/backtest/backtests/${created.id}`);
        onProgress?.(current.progress);
        if (current.status === "FAILED") throw new Error(current.error ?? "Бэктест завершился с ошибкой");
        if (current.status === "COMPLETED") {
          completed = current;
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
      }
      if (!completed?.result) throw new Error("Расчёт выполняется дольше часа. Его результат останется в истории запусков.");
      return mapBacktestResult(completed.result);
    } finally { /* the caller owns its loading state */ }
  };

  const run = async () => {
    setIsRunning(true); setError(""); setProgress(0);
    try {
      const completed = await executeBacktest(settings, { from: testFrom, to: testTo }, setProgress);
      setResult(completed); setWorkspaceTab(2); runsResource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setIsRunning(false); }
  };

  const openRun = async (runId: string) => {
    setError("");
    try {
      const runDetails = await api<BacktestRun>(`/api/v1/backtest/backtests/${runId}`);
      if (runDetails.result) { setResult(mapBacktestResult(runDetails.result)); setWorkspaceTab(2); }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const exportRun = async (runId: string, format: "csv" | "json") => {
    try {
      const blob = await downloadApi(`/api/v1/backtest/backtests/${runId}/export?format=${format}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `backtest-${runId}.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const repeatRun = async (runId: string) => {
    setError("");
    try {
      const runDetails = await api<BacktestRun>(`/api/v1/backtest/backtests/${runId}`);
      const request = runDetails.result?.request_config;
      if (!request) throw new Error("В этом отчёте отсутствуют сохранённые параметры запуска");
      restoredConfig.current = request.config;
      restoredModelVersion.current = request.model_version;
      setAsset(request.symbol);
      setSelectedTimeframes(request.timeframes.length ? request.timeframes : [request.timeframe]);
      setCandleLimit(request.candle_limit);
      if (typeof request.train_from === "number") setTrainFrom(savedDate(request.train_from));
      if (typeof request.train_to === "number") setTrainTo(savedDate(request.train_to));
      if (typeof request.test_from === "number") setTestFrom(savedDate(request.test_from));
      if (typeof request.test_to === "number") setTestTo(savedDate(request.test_to));
      setSettings((current) => restoreSettings(request, current));
      setProgress(0);
      setWorkspaceTab(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const copyRunConfig = async (runId: string) => {
    setError("");
    setHistoryBusy(true);
    try {
      const runDetails = await api<BacktestRun>(`/api/v1/backtest/backtests/${runId}`);
      const request = runDetails.result?.request_config;
      if (!request) throw new Error("В этом отчёте отсутствует сохранённая конфигурация");
      await navigator.clipboard.writeText(JSON.stringify(request, null, 2));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setHistoryBusy(false); }
  };

  const pasteRunConfig = async () => {
    setError("");
    setHistoryBusy(true);
    try {
      const parsed = JSON.parse(await navigator.clipboard.readText()) as SavedBacktestRequest;
      if (!parsed || typeof parsed.symbol !== "string" || !parsed.config || typeof parsed.config !== "object") {
        throw new Error("В буфере обмена нет корректной конфигурации бэктеста");
      }
      restoredConfig.current = parsed.config;
      restoredModelVersion.current = parsed.model_version;
      setAsset(parsed.symbol);
      setSelectedTimeframes(parsed.timeframes?.length ? parsed.timeframes : [parsed.timeframe]);
      setCandleLimit(parsed.candle_limit);
      if (typeof parsed.train_from === "number") setTrainFrom(savedDate(parsed.train_from));
      if (typeof parsed.train_to === "number") setTrainTo(savedDate(parsed.train_to));
      if (typeof parsed.test_from === "number") setTestFrom(savedDate(parsed.test_from));
      if (typeof parsed.test_to === "number") setTestTo(savedDate(parsed.test_to));
      setSettings((current) => restoreSettings(parsed, current));
      setProgress(0);
      setWorkspaceTab(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setHistoryBusy(false); }
  };

  const deleteRuns = async (runs: BacktestRun[]) => {
    const label = runs.length === 1 ? "этот отчёт" : `${runs.length} отчётов`;
    if (!window.confirm(`Удалить ${label}? Это действие нельзя отменить.`)) return;
    setError("");
    setHistoryBusy(true);
    try {
      await Promise.all(runs.map((runItem) => api(`/api/v1/backtest/backtests/${runItem.id}`, { method: "DELETE" })));
      setComparison((current) => current.filter((item) => !runs.some((deleted) => deleted.id === item.id)));
      runsResource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      runsResource.reload();
    } finally { setHistoryBusy(false); }
  };

  const compareRuns = async (ids: string[]) => {
    try {
      const query = ids.map((id) => `ids=${encodeURIComponent(id)}`).join("&");
      const response = await api<{ runs: BacktestRun[] }>(`/api/v1/backtest/backtests/compare?${query}`);
      setComparison(response.runs);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return <SectionPage wide title="Бэктест" description="Проверка торговых стратегий на исторических данных без отправки ордеров.">
    <Paper variant="outlined" sx={{ mb: 2, px: { xs: 1, md: 2 }, bgcolor: "background.paper" }}>
      <Tabs value={workspaceTab} onChange={(_,value) => setWorkspaceTab(value)} variant="scrollable" scrollButtons="auto">
        <Tab label="1. Данные" /><Tab label="2. Настройка и запуск" />
        <Tab label={result ? "3. Результаты" : "3. Результаты · нет данных"} />
        <Tab label="4. История запусков" />
        <Tab label="5. Перебор параметров" />
      </Tabs>
    </Paper>
    {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
    {workspaceTab === 0 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
    <Paper variant="outlined" sx={{ p: 3, mb: 1.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Активы и исторические данные</Typography>
      <AssetManager
        addAsset={addAsset}
        assets={assets}
        removeAsset={removeAsset}
        selectedAsset={selectedAsset}
        onSelect={setAsset}
        onAssetsChanged={reloadAssets}
      />
      <DatasetOverview assets={assets} canManage={roles.includes("admin")} selectedAsset={selectedAsset} />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 2.5 }}>
        <Alert severity="info" sx={{ flex: 1 }}>
          Роли таймфреймов задаются шаблонами. Для точного исполнения сделок автоматически используется самый младший выбранный ТФ.
        </Alert>
        <TextField
          label="Количество свечей"
          value={candleLimit}
          type="number"
          onChange={(event) => setCandleLimit(Number(event.target.value))}
          helperText={`Нужно до ${requiredTestCandleLimit.toLocaleString("ru-RU")}; при запуске лимит увеличится автоматически`}
          slotProps={{ htmlInput: { min: 100, max: 2_000_000 } }}
        />
        <Button variant="outlined" onClick={() => setCandleLimit(requiredTestCandleLimit)}>
          Рассчитать лимит бэктеста
        </Button>
      </Stack>
      <FormGroup row sx={{ mt: 1 }}>
        {timeframes.map((item) => <FormControlLabel key={item} label={item} control={<Checkbox
          checked={selectedTimeframes.includes(item)}
          disabled={selectedTimeframes.length === 1 && selectedTimeframes.includes(item)}
          onChange={(event) => setSelectedTimeframes((current) => event.target.checked
            ? [...current, item]
            : current.filter((value) => value !== item))}
        />} />)}
      </FormGroup>
      <Typography variant="subtitle2" sx={{ mt: 2.5, mb: 1 }}>Периоды без пересечения</Typography>
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Обучение: начало" value={trainFrom}
            onChange={(event) => setTrainFrom(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Обучение: конец" value={trainTo}
            onChange={(event) => setTrainTo(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Бэктест: начало" value={testFrom}
            onChange={(event) => setTestFrom(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Бэктест: конец" value={testTo}
            onChange={(event) => setTestTo(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
      </Grid>
      <FormControlLabel
        sx={{ mt: 1 }}
        control={<Checkbox checked={settings.localRetraining} onChange={(event) => setSettings({
          ...settings,
          localRetraining: event.target.checked,
        })} />}
        label="Локально переобучить модель только на обучающем периоде"
      />
      <HistoryLoader
        canManage={roles.includes("admin")}
        symbol={selectedAsset}
        timeframes={selectedTimeframes}
        from={trainFrom}
        to={testTo}
      />
    </Paper>
    </Box>}
    {workspaceTab === 1 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
      <Grid container spacing={2}>
      <Grid size={{ xs: 12, xl: 5 }}>
        <BacktestSettingsForm
          settings={settings}
          onChange={setSettings}
          onRun={() => void run()}
          isRunning={isRunning}
          progress={progress}
          templates={templates}
        />
      </Grid>
      <Grid size={{ xs: 12, xl: 7 }}>
        <Paper variant="outlined" sx={{ p: 3, position: { xl: "sticky" }, top: { xl: 16 } }}>
          <Typography variant="h5">Параметры запуска</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>
            {selectedAsset} · {selectedTimeframes.join(", ")} · тест {testFrom} — {testTo}
          </Typography>
          <Alert severity={isRunning ? "warning" : "info"} sx={{ mt: 2 }}>
            {isRunning ? `Расчёт выполняется: ${progress}%` : "После завершения система автоматически откроет вкладку результатов."}
          </Alert>
          <Button variant="outlined" sx={{ mt: 2 }} onClick={() => setWorkspaceTab(0)}>Изменить данные и периоды</Button>
        </Paper>
      </Grid>
    </Grid>
    </Box>}
    {workspaceTab === 2 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
      {result ? <BacktestReport result={result} /> : <Paper variant="outlined" sx={{ minHeight: 420, display: "grid", placeContent: "center", textAlign: "center", p: 3 }}>
        <Typography variant="h5">Результатов пока нет</Typography>
        <Typography color="text.secondary" sx={{ mt: 1 }}>Настройте данные и выполните бэктест.</Typography>
        <Button variant="contained" sx={{ mt: 2 }} onClick={() => setWorkspaceTab(1)}>Перейти к запуску</Button>
      </Paper>}
    </Box>}
    {workspaceTab === 3 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
    <BacktestHistory
      busy={historyBusy}
      loading={runsResource.isLoading}
      runs={runsResource.data?.runs ?? []}
      total={runsResource.data?.total ?? 0}
      page={historyPage}
      rowsPerPage={historyRowsPerPage}
      onPageChange={setHistoryPage}
      onRowsPerPageChange={(value) => { setHistoryRowsPerPage(value); setHistoryPage(0); }}
      onCopy={(runItem) => void copyRunConfig(runItem.id)}
      onDelete={(runItems) => void deleteRuns(runItems)}
      onOpen={(runItem) => void openRun(runItem.id)}
      onPaste={() => void pasteRunConfig()}
      onRepeat={(runItem) => void repeatRun(runItem.id)}
      onExport={(runItem, format) => void exportRun(runItem.id, format)}
      onCompare={(ids) => void compareRuns(ids)}
    />
    {comparison.length > 1 && <Paper variant="outlined" sx={{ p: 2.5, mt: 1.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Сравнение запусков</Typography>
      <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
        {comparison.map((runItem) => <Paper key={runItem.id} variant="outlined" sx={{ p: 2, flex: 1 }}>
          <Typography sx={{ fontWeight: 650 }}>{runItem.symbol} · {runItem.timeframe}</Typography>
          <Typography>Доходность: {runItem.result?.total_return_percent.toFixed(2)}%</Typography>
          <Typography>Просадка: {runItem.result?.max_drawdown_percent.toFixed(2)}%</Typography>
          <Typography>Сделок: {runItem.result?.total_trades}</Typography>
        </Paper>)}
      </Stack>
    </Paper>}
    </Box>}
    <Box sx={{
      display: workspaceTab === 4 ? "block" : "none",
      p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover",
    }}>
      <BacktestOptimizer
        settings={settings}
        assets={assets}
        initialAsset={selectedAsset}
        initialTimeframes={selectedTimeframes}
        testFrom={testFrom}
        testTo={testTo}
        runCandidate={async (candidateSettings, period, optimizerAsset, optimizerTimeframes) => {
          const candidateResult = await executeBacktest(
            candidateSettings, period, undefined, optimizerAsset, optimizerTimeframes, false,
          );
          runsResource.reload();
          return candidateResult;
        }}
        onApply={(candidateSettings, candidateResult) => {
          setSettings(candidateSettings);
          setResult(candidateResult);
          setWorkspaceTab(2);
        }}
      />
    </Box>
  </SectionPage>;
}
