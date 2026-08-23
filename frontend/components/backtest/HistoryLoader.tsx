"use client";

import { Alert, Button, LinearProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { api } from "../../lib/api";
import { useApiResource } from "../../hooks/useApiResource";

interface HistoryJob {
  error?: string;
  id: string;
  ingested: number;
  progress: number;
  requests: number;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
}

interface HistoryLoaderProps {
  canManage: boolean;
  from: string;
  symbol: string;
  timeframes: string[];
  to: string;
}

interface DatasetResponse {
  timeframes: Array<{ candles: number; from_timestamp: number; timeframe: string; to_timestamp: number }>;
}

export function HistoryLoader({ canManage, from, symbol, timeframes, to }: HistoryLoaderProps) {
  const [maximum, setMaximum] = useState(10_000);
  const [job, setJob] = useState<HistoryJob>();
  const [error, setError] = useState("");
  const dataset = useApiResource<DatasetResponse>(`/api/v1/backtest/datasets/${encodeURIComponent(symbol)}`);

  const start = async () => {
    setError("");
    try {
      const created = await api<HistoryJob>("/api/v1/exchange/exchange/history", {
        method: "POST",
        body: JSON.stringify({
          symbol,
          timeframes,
          from_timestamp: Date.parse(`${from}T00:00:00Z`),
          to_timestamp: Date.parse(`${to}T23:59:59Z`),
          max_candles_per_timeframe: maximum,
        }),
      });
      setJob(created);
      for (let attempt = 0; attempt < 3600; attempt += 1) {
        const current = await api<HistoryJob>(`/api/v1/exchange/exchange/history/${created.id}`);
        setJob(current);
        if (current.status === "FAILED") throw new Error(current.error ?? "Ошибка загрузки OKX");
        if (current.status === "COMPLETED") {
          dataset.reload();
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  return <Paper variant="outlined" sx={{ p: 2.5, mt: 2 }}>
    <Typography variant="h6">История OKX</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
      Сервис загружает по 300 закрытых свечей за запрос и автоматически двигается назад по истории.
    </Typography>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
      <TextField label="Максимум на каждый ТФ" type="number" value={maximum}
        onChange={(event) => setMaximum(Number(event.target.value))} slotProps={{ htmlInput: { min: 1, max: 1_000_000 } }} />
      <Button variant="contained" disabled={!canManage || active || maximum < 1} onClick={() => void start()}>
        {active ? "Загружаем…" : "Загрузить свечи"}
      </Button>
    </Stack>
    {job && <Stack spacing={0.75} sx={{ mt: 2 }}>
      <LinearProgress variant="determinate" value={job.progress} />
      <Typography variant="caption">{job.status} · сохранено {job.ingested} · запросов к OKX: {job.requests}</Typography>
    </Stack>}
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1, mt: 2 }}>
      {(dataset.data?.timeframes ?? []).map((item) => (
        <Typography key={item.timeframe} variant="caption">
          {item.timeframe}: {item.candles.toLocaleString("ru-RU")}
        </Typography>
      ))}
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
  </Paper>;
}
