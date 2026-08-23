"use client";

import { Alert, Grid, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { AssetManager } from "../../components/backtest/AssetManager";
import { BacktestReport } from "../../components/backtest/BacktestReport";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { api } from "../../lib/api";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { runBacktest } from "../../lib/backtest/engine";
import type { BacktestResult, BacktestSettings } from "../../lib/backtest/types";
import type { CandlesResponse } from "../../lib/types";

const defaultSettings: BacktestSettings = {
  initialCapital: 10_000,
  fastPeriod: 9,
  slowPeriod: 21,
  feePercent: 0.05,
  slippagePercent: 0.02,
  stopLossPercent: 2,
  takeProfitPercent: 4,
  positionSizePercent: 25,
  directionMode: "BOTH",
};

const timeframes = ["M1", "M5", "M15", "H1", "H4", "D1"];

export default function BacktestPage() {
  const [asset, setAsset] = useState("BTC-USDT-SWAP");
  const { assets } = useTradingAssets();
  const [timeframe, setTimeframe] = useState("M15");
  const [candleLimit, setCandleLimit] = useState(1000);
  const [settings, setSettings] = useState(defaultSettings);
  const [result, setResult] = useState<BacktestResult>();
  const [error, setError] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const selectedAsset = assets.includes(asset) ? asset : assets[0];

  const run = async () => {
    setIsRunning(true);
    setError("");
    try {
      const query = `symbol=${encodeURIComponent(selectedAsset)}&timeframe=${timeframe}&limit=${candleLimit}`;
      const response = await api<CandlesResponse>(`/api/v1/data/market/candles?${query}`);
      if (response.candles.length <= settings.slowPeriod + 1) {
        throw new Error(`Недостаточно свечей: получено ${response.candles.length}, требуется больше ${settings.slowPeriod + 1}`);
      }
      setResult(runBacktest({ candles: response.candles, settings }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsRunning(false);
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
    </Paper>
    {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 12, lg: 4 }}>
        <BacktestSettingsForm settings={settings} onChange={setSettings} onRun={() => void run()} isRunning={isRunning} />
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
  </SectionPage>;
}
