"use client";

import { Alert, Checkbox, FormControlLabel, Grid, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { AssetManager } from "../../components/backtest/AssetManager";
import { BacktestReport } from "../../components/backtest/BacktestReport";
import { BacktestHistory } from "../../components/backtest/BacktestHistory";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { api, downloadApi } from "../../lib/api";
import { useApiResource } from "../../hooks/useApiResource";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { mapBacktestResult } from "../../lib/backtest/apiTypes";
import type { BacktestCreateResponse, BacktestRun, BacktestRunsResponse } from "../../lib/backtest/apiTypes";
import type { BacktestResult, BacktestSettings } from "../../lib/backtest/types";

const defaultSettings: BacktestSettings = {
  initialCapital: 10_000,
  strategy: "SMC",
  fastPeriod: 9,
  slowPeriod: 21,
  feePercent: 0.05,
  slippagePercent: 0.02,
  stopLossPercent: 2,
  takeProfitPercent: 4,
  positionSizePercent: 25,
  leverage: 1,
  maintenanceMarginPercent: 0.5,
  fundingPercentPerDay: 0,
  trailingStopPercent: undefined,
  directionMode: "BOTH",
  riskPerTradePercent: 1,
  kellyFraction: 0.25,
  confidenceThreshold: 0.6,
  templateIds: ["OB_FVG_REVERSAL"],
  localRetraining: true,
};

const timeframes = ["M1", "M5", "M15", "H1", "H4", "D1"];

export default function BacktestPage() {
  const [asset, setAsset] = useState("BTC-USDT-SWAP");
  const { assets } = useTradingAssets();
  const [timeframe, setTimeframe] = useState("M15");
  const [candleLimit, setCandleLimit] = useState(1000);
  const today = new Date().toISOString().slice(0, 10);
  const [trainFrom, setTrainFrom] = useState("2025-01-01");
  const [trainTo, setTrainTo] = useState("2025-06-30");
  const [testFrom, setTestFrom] = useState("2025-07-01");
  const [testTo, setTestTo] = useState(today);
  const [settings, setSettings] = useState(defaultSettings);
  const [result, setResult] = useState<BacktestResult>();
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const runsResource = useApiResource<BacktestRunsResponse>("/api/v1/backtest/backtests");
  const selectedAsset = assets.includes(asset) ? asset : assets[0];

  const run = async () => {
    setIsRunning(true);
    setError("");
    try {
      setProgress(0);
      const created = await api<BacktestCreateResponse>("/api/v1/backtest/backtests", {
        method: "POST",
        body: JSON.stringify({
          symbol: selectedAsset,
          timeframe,
          timeframes,
          candle_limit: candleLimit,
          train_from: Date.parse(`${trainFrom}T00:00:00Z`),
          train_to: Date.parse(`${trainTo}T23:59:59Z`),
          test_from: Date.parse(`${testFrom}T00:00:00Z`),
          test_to: Date.parse(`${testTo}T23:59:59Z`),
          config: {
            strategy: settings.strategy,
            initial_capital: settings.initialCapital,
            position_size_percent: settings.positionSizePercent,
            leverage: settings.leverage,
            maintenance_margin_percent: settings.maintenanceMarginPercent,
            fee_percent: settings.feePercent,
            slippage_percent: settings.slippagePercent,
            funding_percent_per_day: settings.fundingPercentPerDay,
            stop_loss_percent: settings.stopLossPercent,
            take_profit_percent: settings.takeProfitPercent,
            trailing_stop_percent: settings.trailingStopPercent,
            fast_period: settings.fastPeriod,
            slow_period: settings.slowPeriod,
            direction_mode: settings.directionMode,
            risk_per_trade_percent: settings.riskPerTradePercent,
            kelly_fraction: settings.kellyFraction,
            confidence_threshold: settings.confidenceThreshold,
            template_ids: settings.templateIds,
            local_retraining: settings.localRetraining,
          },
        }),
      });
      let completed: BacktestRun | undefined;
      for (let attempt = 0; attempt < 120; attempt += 1) {
        const current = await api<BacktestRun>(`/api/v1/backtest/backtests/${created.id}`);
        setProgress(current.progress);
        if (current.status === "FAILED") throw new Error(current.error ?? "Бэктест завершился с ошибкой");
        if (current.status === "COMPLETED") {
          completed = current;
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
      if (!completed?.result) throw new Error("Превышено время ожидания результата");
      setResult(mapBacktestResult(completed.result));
      runsResource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsRunning(false);
    }
  };

  const openRun = async (runId: string) => {
    setError("");
    try {
      const runDetails = await api<BacktestRun>(`/api/v1/backtest/backtests/${runId}`);
      if (runDetails.result) setResult(mapBacktestResult(runDetails.result));
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

  return <SectionPage title="Бэктест" description="Проверка торговых стратегий на исторических данных без отправки ордеров.">
    <Paper variant="outlined" sx={{ p: 3, mb: 1.5 }}>
      <Typography variant="h6" sx={{ mb: 2 }}>Активы и исторические данные</Typography>
      <AssetManager selectedAsset={selectedAsset} onSelect={setAsset} />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 2.5 }}>
        <TextField select label="Таймфрейм" value={timeframe} onChange={(event) => setTimeframe(event.target.value)} sx={{ minWidth: 150 }}>
          {timeframes.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>
        <TextField
          label="Количество свечей"
          value={candleLimit}
          type="number"
          onChange={(event) => setCandleLimit(Number(event.target.value))}
          slotProps={{ htmlInput: { min: 100, max: 1000 } }}
        />
      </Stack>
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
    </Paper>
    {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 12, lg: 4 }}>
        <BacktestSettingsForm
          settings={settings}
          onChange={setSettings}
          onRun={() => void run()}
          isRunning={isRunning}
          progress={progress}
        />
      </Grid>
      <Grid size={{ xs: 12, lg: 8 }}>
        {result ? <BacktestReport result={result} /> : (
          <Paper variant="outlined" sx={{ minHeight: 420, display: "grid", placeContent: "center", textAlign: "center", p: 3 }}>
          <Typography variant="h5">Настройте стратегию и запустите расчёт</Typography>
          <Typography color="text.secondary" sx={{ mt: 1 }}>Здесь появятся метрики, кривая капитала и журнал сделок.</Typography>
          </Paper>
        )}
      </Grid>
    </Grid>
    <BacktestHistory
      runs={runsResource.data?.runs ?? []}
      onOpen={(runItem) => void openRun(runItem.id)}
      onExport={(runItem, format) => void exportRun(runItem.id, format)}
    />
  </SectionPage>;
}
