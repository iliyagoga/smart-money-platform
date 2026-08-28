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
import type { BacktestCreateResponse, BacktestRun, BacktestRunsResponse } from "../../lib/backtest/apiTypes";
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
  const runsResource = useApiResource<BacktestRunsResponse>("/api/v1/backtest/backtests");
  const templatesResource = useApiResource<ScenarioTemplatesResponse>("/api/v1/smc/scenario-templates");
  const templateSelectionInitialized = useRef(false);
  const templates = useMemo(() => templatesResource.data?.templates ?? [], [templatesResource.data?.templates]);
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
          config: {
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
      runs={runsResource.data?.runs ?? []}
      onOpen={(runItem) => void openRun(runItem.id)}
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
