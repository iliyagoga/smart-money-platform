"use client";

import { Alert, Box, Button, Checkbox, FormControlLabel, FormGroup, Grid, Paper, Stack, Tab, Tabs, TextField, Typography } from "@mui/material";
import { useEffect, useRef, useState } from "react";
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
import { mergeSettingsConfig } from "../../lib/backtest/configClipboard";
import { toBackendBacktestConfig } from "../../lib/backtest/backendConfig";
import { defaultBacktestSettings as defaultSettings } from "../../lib/backtest/defaultSettings";
import { useAuth } from "../../components/auth/AuthProvider";
import { useRouter } from "next/navigation";

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
  return {
    ...current,
    initialCapital: savedNumber(config.initial_capital, current.initialCapital),
    strategy: "ELLIOTT",
    feePercent: savedNumber(config.fee_percent, current.feePercent),
    makerFeePercent: savedNumber(config.maker_fee_percent, current.makerFeePercent ?? current.feePercent),
    takerFeePercent: savedNumber(config.taker_fee_percent, current.takerFeePercent ?? current.feePercent),
    slippagePercent: savedNumber(config.slippage_percent, current.slippagePercent),
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
    directionMode: typeof config.direction_mode === "string" ? config.direction_mode as BacktestSettings["directionMode"] : current.directionMode,
    riskPerTradePercent: savedNumber(config.risk_per_trade_percent, current.riskPerTradePercent),
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
      breakoutBufferAtr: savedNumber(elliott.breakout_buffer_atr, current.elliott.breakoutBufferAtr),
      retestZoneAtr: savedNumber(elliott.retest_zone_atr, current.elliott.retestZoneAtr),
      displacementMinAtr: savedNumber(elliott.displacement_min_atr, current.elliott.displacementMinAtr),
      displacementMinBodyRatio: savedNumber(elliott.displacement_min_body_ratio, current.elliott.displacementMinBodyRatio),
      displacementRetracement: savedNumber(elliott.displacement_retracement, current.elliott.displacementRetracement),
      sweepMinWickRatio: savedNumber(elliott.sweep_min_wick_ratio, current.elliott.sweepMinWickRatio),
      volatilityExpansionRatio: savedNumber(elliott.volatility_expansion_ratio, current.elliott.volatilityExpansionRatio),
      volumeExpansionRatio: savedNumber(elliott.volume_expansion_ratio, current.elliott.volumeExpansionRatio),
      volumeExpansionMinBodyRatio: savedNumber(
        elliott.volume_expansion_min_body_ratio, current.elliott.volumeExpansionMinBodyRatio,
      ),
      chochMinAtr: savedNumber(elliott.choch_min_atr, current.elliott.chochMinAtr),
      chochMinBodyRatio: savedNumber(elliott.choch_min_body_ratio, current.elliott.chochMinBodyRatio),
      macroFilter: typeof elliott.macro_filter === "string" ? elliott.macro_filter as BacktestSettings["elliott"]["macroFilter"] : current.elliott.macroFilter,
      adxPeriod: savedNumber(elliott.adx_period, current.elliott.adxPeriod),
      adxMin: savedNumber(elliott.adx_min, current.elliott.adxMin),
      requireDiConfirmation: savedBoolean(elliott.require_di_confirmation, current.elliott.requireDiConfirmation),
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

export default function BacktestPage() {
  const router=useRouter();
  const { roles } = useAuth();
  const [asset, setAsset] = useState("");
  const { addAsset, assetDetails, assets, reload: reloadAssets, removeAsset } = useTradingAssets();
  const [selectedTimeframes, setSelectedTimeframes] = useState(timeframes);
  const [okxAsset, setOkxAsset] = useState("");
  const [okxTimeframes] = useState(timeframes);
  const [candleLimit, setCandleLimit] = useState(10_000);
  const today = new Date().toISOString().slice(0, 10);
  const [testFrom, setTestFrom] = useState("2025-07-01");
  const [testTo, setTestTo] = useState(today);
  const [dataFrom, setDataFrom] = useState("2024-01-01");
  const [dataTo, setDataTo] = useState(today);
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
  const runsResource = useApiResource<BacktestRunsResponse>(
    `/api/v1/backtest/backtests?limit=${historyRowsPerPage}&offset=${historyPage * historyRowsPerPage}`,
    350,
  );
  useEffect(() => {
    const lastPage = Math.max(0, Math.ceil((runsResource.data?.total ?? 0) / historyRowsPerPage) - 1);
    if (historyPage > lastPage) setHistoryPage(lastPage);
  }, [historyPage, historyRowsPerPage, runsResource.data?.total]);
  const selectedAsset = asset || assets[0];
  const selectedOkxAsset = okxAsset || assets[0];
  useEffect(() => {
    if (!okxAsset && assets.length) setOkxAsset(assets[0]);
  }, [assets, okxAsset]);
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
    persistResult = true,
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
          test_from: Date.parse(`${period.from}T00:00:00Z`),
          test_to: Date.parse(`${period.to}T23:59:59Z`),
          config: toBackendBacktestConfig(candidateSettings, {
            tickSize: runAssetDetails?.tick_size,
            lotSize: runAssetDetails?.lot_size,
            minimumOrderSize: runAssetDetails?.minimum_order_size,
          }, restoredConfig.current),
        }),
      });
      let completed: BacktestRun | undefined;
      for (let attempt = 0; attempt < 3_600; attempt += 1) {
        const current = await api<BacktestRun>(`/api/v1/backtest/backtests/${created.id}`);
        onProgress?.(current.progress);
        if (current.status === "FAILED") {
          if (!persistResult) await api(`/api/v1/backtest/backtests/${created.id}`, { method: "DELETE" });
          throw new Error(current.error ?? "Бэктест завершился с ошибкой");
        }
        if (current.status === "COMPLETED") {
          completed = current;
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1_000));
      }
      if (!completed?.result) throw new Error("Расчёт выполняется дольше часа. Его результат останется в истории запусков.");
      const mapped = mapBacktestResult(completed.result);
      if (!persistResult) await api(`/api/v1/backtest/backtests/${created.id}`, { method: "DELETE" });
      return mapped;
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
      setAsset(request.symbol);
      setSelectedTimeframes(request.timeframes.length ? request.timeframes : [request.timeframe]);
      setCandleLimit(request.candle_limit);
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
      const config=mergeSettingsConfig(defaultSettings,request.config);
      await navigator.clipboard.writeText(JSON.stringify(config, null, 2));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setHistoryBusy(false); }
  };

  const pasteRunConfig = async () => {
    setError("");
    setHistoryBusy(true);
    try {
      const parsed = JSON.parse(await navigator.clipboard.readText()) as unknown;
      setSettings((current) => mergeSettingsConfig(current, parsed));
      setProgress(0);
      setWorkspaceTab(1);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setHistoryBusy(false); }
  };
  const saveRunConfiguration = async (runId:string) => {
    setError("");setHistoryBusy(true);
    try {
      const runDetails=await api<BacktestRun>(`/api/v1/backtest/backtests/${runId}`);
      const request=runDetails.result?.request_config;
      if (!request) throw new Error("В этом прогоне отсутствует сохранённая конфигурация");
      sessionStorage.setItem("configuration-import",JSON.stringify({
        name:`${request.symbol} Elliott ${new Date(runDetails.created_at).toLocaleDateString("ru-RU")}`,
        description:`Из бэктеста ${request.symbol} · ${request.timeframes?.join(", ") || request.timeframe}`,
        request,
      }));
      router.push("/configurations");
    } catch(reason) { setError(reason instanceof Error ? reason.message:String(reason));setHistoryBusy(false); }
  };

  const deleteRunsInPeriod = async (from: string, to: string): Promise<number | undefined> => {
    if (!window.confirm(`Удалить все отчёты, созданные с ${from} по ${to} включительно, на всех страницах? Активные запуски сохранятся. Это действие нельзя отменить.`)) return;
    setError("");
    setHistoryBusy(true);
    try {
      const start = new Date(`${from}T00:00:00`);
      const end = new Date(`${to}T00:00:00`);
      end.setDate(end.getDate() + 1);
      const query = new URLSearchParams({ date_from: start.toISOString(), date_to: end.toISOString() });
      const response = await api<{ deleted_count: number }>(`/api/v1/backtest/backtests?${query}`, { method: "DELETE" });
      setComparison((current) => current.filter((item) => {
        const created = new Date(item.created_at);
        return created < start || created >= end;
      }));
      setHistoryPage(0);
      runsResource.reload();
      return response.deleted_count;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      runsResource.reload();
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

  return <SectionPage title="Бэктест" description="Проверка торговых стратегий на исторических данных без отправки ордеров.">
    <Paper variant="outlined" sx={{ mb: 2, px: { xs: 1, md: 2 }, bgcolor: "background.paper" }}>
      <Tabs value={workspaceTab} onChange={(_,value) => setWorkspaceTab(value)} variant="scrollable" scrollButtons="auto">
        <Tab label="1. Данные" /><Tab label="2. Настройка и запуск" />
        <Tab label={result ? "3. Результаты" : "3. Результаты · нет данных"} />
        <Tab label="4. История запусков" />
        <Tab label="5. Перебор параметров" />
        <Tab label="6. Данные OKX" />
      </Tabs>
    </Paper>
    {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
    {workspaceTab === 0 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
    <Paper variant="outlined" sx={{ p: 2, mb: 1.5 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>Актив и параметры периода</Typography>
      <AssetManager
        addAsset={addAsset}
        assets={assets}
        removeAsset={removeAsset}
        selectedAsset={selectedAsset}
        onSelect={setAsset}
        onAssetsChanged={reloadAssets}
      />
      <DatasetOverview assets={selectedAsset ? [selectedAsset] : []} canManage={false} selectedAsset={selectedAsset} />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 1.5 }}>
        <TextField
          label="Количество свечей"
          value={candleLimit}
          type="number"
          onChange={(event) => setCandleLimit(Number(event.target.value))}
          helperText={`Нужно до ${requiredTestCandleLimit.toLocaleString("ru-RU")}; при запуске лимит увеличится автоматически`}
          slotProps={{ htmlInput: { min: 100, max: 2_000_000 } }}
        />
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
      <Typography variant="subtitle2" sx={{ mt: 1.5, mb: 1 }}>Период бэктеста</Typography>
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Бэктест: начало" value={testFrom}
            onChange={(event) => setTestFrom(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
          <TextField fullWidth type="date" label="Бэктест: конец" value={testTo}
            onChange={(event) => setTestTo(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Grid>
      </Grid>
    </Paper>
    </Box>}
    {workspaceTab === 1 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
      <Grid container spacing={2}>
      <Grid size={{ xs: 12 }} sx={{ maxWidth: 1100, mx: "auto" }}>
        <Button variant="outlined" disabled={isRunning || historyBusy} onClick={() => void pasteRunConfig()} sx={{ mb: 1.5 }}>
          Вставить конфигурацию в настройки
        </Button>
        <BacktestSettingsForm
          settings={settings}
          onChange={setSettings}
          onRun={() => void run()}
          isRunning={isRunning}
          progress={progress}
        />
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
      onDeletePeriod={deleteRunsInPeriod}
      onDelete={(runItems) => void deleteRuns(runItems)}
      onOpen={(runItem) => void openRun(runItem.id)}
      onRepeat={(runItem) => void repeatRun(runItem.id)}
      onSaveConfiguration={(runItem) => void saveRunConfiguration(runItem.id)}
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
        key={`${selectedAsset}:${testFrom}:${testTo}:${JSON.stringify(settings)}`}
        settings={settings}
        initialAsset={selectedAsset}
        testFrom={testFrom}
        testTo={testTo}
        runCandidate={async (candidateSettings, period, optimizerAsset, optimizerTimeframes, persistResult = false) => {
          const candidateResult = await executeBacktest(
            candidateSettings, period, undefined, optimizerAsset, optimizerTimeframes, persistResult,
          );
          if (persistResult) runsResource.reload();
          return candidateResult;
        }}
        onApply={(candidateSettings, candidateResult) => {
          setSettings(candidateSettings);
          setResult(candidateResult);
          setWorkspaceTab(2);
        }}
      />
    </Box>
    {workspaceTab === 5 && <Box sx={{ p: { xs: 1, md: 2 }, borderRadius: 2, bgcolor: "action.hover" }}>
      <Paper variant="outlined" sx={{ p: 2.5, mb: 1.5 }}>
        <Typography variant="h6" sx={{ mb: 1.5 }}>Параметры запроса к OKX</Typography>
        <AssetManager
          addAsset={addAsset}
          assets={assets}
          removeAsset={removeAsset}
          selectedAsset={selectedOkxAsset}
          onSelect={setOkxAsset}
          onAssetsChanged={reloadAssets}
        />
      </Paper>
      <DatasetOverview assets={assets} canManage={roles.includes("admin")} selectedAsset={selectedOkxAsset} />
      <Paper variant="outlined" sx={{ p: 2.5, mb: 1.5 }}>
        <Typography variant="h6" sx={{ mb: 0.75 }}>Период запроса к OKX</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Этот период независим от периода бэктеста. Для догрузки назад укажите более раннюю дату начала.
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
          <TextField fullWidth type="date" label="Начало загрузки" value={dataFrom}
            onChange={(event) => setDataFrom(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          <TextField fullWidth type="date" label="Конец загрузки" value={dataTo}
            onChange={(event) => setDataTo(event.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
        </Stack>
      </Paper>
      <HistoryLoader
        canManage={roles.includes("admin")}
        symbol={selectedOkxAsset}
        timeframes={okxTimeframes}
        from={dataFrom}
        to={dataTo}
      />
    </Box>}
  </SectionPage>;
}
