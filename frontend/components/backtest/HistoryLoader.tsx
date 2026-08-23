"use client";

import { Alert, Button, LinearProgress, Paper, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApiResource } from "../../hooks/useApiResource";

interface HistoryJob {
  error?: string;
  id: string;
  ingested: number;
  progress: number;
  requests: number;
  symbol: string;
  status: "QUEUED" | "RUNNING" | "PAUSED" | "CANCELLED" | "COMPLETED" | "FAILED";
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

interface HistoryJobsResponse { jobs: HistoryJob[] }

export function HistoryLoader({ canManage, from, symbol, timeframes, to }: HistoryLoaderProps) {
  const [maximum, setMaximum] = useState(10_000);
  const [job, setJob] = useState<HistoryJob>();
  const [error, setError] = useState("");
  const { data: dataset, reload: reloadDataset } = useApiResource<DatasetResponse>(
    `/api/v1/backtest/datasets/${encodeURIComponent(symbol)}`,
  );
  const intervals: Record<string, number> = {
    D1: 86_400_000,
    H1: 3_600_000,
    H4: 14_400_000,
    M1: 60_000,
    M15: 900_000,
    M5: 300_000,
  };
  const rangeMilliseconds = Math.max(0, Date.parse(`${to}T23:59:59Z`) - Date.parse(`${from}T00:00:00Z`));
  const requiredMaximum = Math.min(1_000_000, Math.max(
    ...timeframes.map((timeframe) => Math.ceil(rangeMilliseconds / intervals[timeframe]) + 2),
  ));
  const formatDate = (timestamp: number) => new Date(timestamp).toLocaleDateString("ru-RU");
  const jobId = job?.id;
  const jobStatus = job?.status;

  useEffect(() => {
    void api<HistoryJobsResponse>("/api/v1/exchange/exchange/history?limit=50").then((response) => {
      setJob(response.jobs.find((item) => item.symbol === symbol));
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [symbol]);

  useEffect(() => {
    if (!jobId || !jobStatus || !["QUEUED", "RUNNING"].includes(jobStatus)) return;
    const timer = window.setInterval(() => {
      void api<HistoryJob>(`/api/v1/exchange/exchange/history/${jobId}`).then((current) => {
        setJob(current);
        if (current.status === "COMPLETED") reloadDataset();
        if (current.status === "FAILED") setError(current.error ?? "Ошибка загрузки OKX");
      }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [jobId, jobStatus, reloadDataset]);

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
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  const control = async (action: "pause" | "resume" | "cancel") => {
    if (!job) return;
    try {
      const changed = await api<HistoryJob>(`/api/v1/exchange/exchange/history/${job.id}/${action}`, { method: "POST" });
      setJob(changed);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
  return <Paper variant="outlined" sx={{ p: 2.5, mt: 2 }}>
    <Typography variant="h6">История OKX</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2 }}>
      Сервис загружает по 300 закрытых свечей за запрос и автоматически двигается назад по истории.
    </Typography>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
      <TextField label="Максимум на каждый ТФ" type="number" value={maximum}
        onChange={(event) => setMaximum(Number(event.target.value))}
        helperText={`Для выбранных дат нужно до ${requiredMaximum.toLocaleString("ru-RU")}`}
        slotProps={{ htmlInput: { min: 1, max: 1_000_000 } }} />
      <Button variant="outlined" onClick={() => setMaximum(requiredMaximum)}>Шаг 1: рассчитать лимит</Button>
      <Button variant="contained" disabled={!canManage || active || maximum < 1} onClick={() => void start()}>
        {active ? "Загружаем…" : "Шаг 2: начать загрузку OKX"}
      </Button>
      {job?.status === "RUNNING" && <Button onClick={() => void control("pause")}>Пауза</Button>}
      {job?.status === "PAUSED" && <Button onClick={() => void control("resume")}>Продолжить</Button>}
      {active && <Button color="error" onClick={() => void control("cancel")}>Отменить</Button>}
    </Stack>
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
      Расчёт меняет только лимит. Загрузка начинается после нажатия синей кнопки «Шаг 2».
    </Typography>
    {job && <Stack spacing={0.75} sx={{ mt: 2 }}>
      <LinearProgress variant="determinate" value={job.progress} />
      <Typography variant="caption">{job.status} · сохранено {job.ingested} · запросов к OKX: {job.requests}</Typography>
    </Stack>}
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1, mt: 2 }}>
      {(dataset?.timeframes ?? []).map((item) => (
        <Typography key={item.timeframe} variant="caption">
          {item.timeframe}: {item.candles.toLocaleString("ru-RU")} · {formatDate(item.from_timestamp)} —
          {` ${formatDate(item.to_timestamp)}`}
        </Typography>
      ))}
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
  </Paper>;
}
