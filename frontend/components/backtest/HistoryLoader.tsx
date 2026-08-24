"use client";

import { Alert, Button, Checkbox, Chip, FormControlLabel, FormGroup, LinearProgress, Paper, Stack, Typography } from "@mui/material";
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
  timeframe_status: Record<string, {
    error?: string;
    ingested: number;
    requests: number;
    status: "QUEUED" | "RUNNING" | "PAUSED" | "CANCELLED" | "COMPLETED" | "FAILED";
  }>;
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
  const [job, setJob] = useState<HistoryJob>();
  const [error, setError] = useState("");
  const [loadTimeframes, setLoadTimeframes] = useState(timeframes);
  const { data: dataset, reload: reloadDataset } = useApiResource<DatasetResponse>(
    `/api/v1/backtest/datasets/${encodeURIComponent(symbol)}`,
  );
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
          timeframes: loadTimeframes,
          from_timestamp: Date.parse(`${from}T00:00:00Z`),
          to_timestamp: Date.parse(`${to}T23:59:59Z`),
        }),
      });
      setJob(created);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const active = job?.status === "QUEUED" || job?.status === "RUNNING";
  const removeTimeframe = async (timeframe: string) => {
    if (!window.confirm(`Удалить все сохранённые свечи ${symbol} · ${timeframe}?`)) return;
    setError("");
    try {
      await api(`/api/v1/backtest/datasets/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(timeframe)}`, {
        method: "DELETE",
      });
      reloadDataset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };
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
      Для каждого выбранного ТФ создаётся отдельная параллельная задача. OKX отдаёт до 300 свечей за запрос.
    </Typography>
    <Typography variant="subtitle2">Таймфреймы для догрузки</Typography>
    <FormGroup row sx={{ mb: 2 }}>
      {["M1","M5","M15","M30","H1","H4","D1"].map((timeframe) => <FormControlLabel key={timeframe}
        label={timeframe} control={<Checkbox checked={loadTimeframes.includes(timeframe)}
          disabled={loadTimeframes.length === 1 && loadTimeframes.includes(timeframe)}
          onChange={(event) => setLoadTimeframes((current) => event.target.checked
            ? [...current,timeframe]
            : current.filter((item) => item !== timeframe))} />} />)}
    </FormGroup>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
      <Button variant="contained" disabled={!canManage || active || !loadTimeframes.length} onClick={() => void start()}>
        {active ? "Загружаем…" : "Загрузить все свечи за период"}
      </Button>
      {job?.status === "RUNNING" && <Button onClick={() => void control("pause")}>Пауза</Button>}
      {job?.status === "PAUSED" && <Button onClick={() => void control("resume")}>Продолжить</Button>}
      {active && <Button color="error" onClick={() => void control("cancel")}>Отменить</Button>}
    </Stack>
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
      Будут запрошены все доступные закрытые свечи между выбранными датами, без расчёта и ограничения количества.
    </Typography>
    {job && <Stack spacing={0.75} sx={{ mt: 2 }}>
      <LinearProgress variant="determinate" value={job.progress} />
      <Typography variant="caption">{job.status} · сохранено {job.ingested} · запросов к OKX: {job.requests}</Typography>
      <Stack spacing={1} sx={{ pt: 1 }}>
        {Object.entries(job.timeframe_status ?? {}).map(([timeframe, item]) => <Paper
          key={timeframe} variant="outlined" sx={{ p: 1.25 }}
        >
          <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", gap: 1 }}>
            <Typography variant="body2" sx={{ fontWeight: 700 }}>{timeframe}</Typography>
            <Chip size="small" label={item.status} color={item.status === "COMPLETED" ? "success" : item.status === "FAILED" ? "error" : "default"} />
          </Stack>
          <LinearProgress
            sx={{ my: 0.75 }}
            variant={item.status === "RUNNING" ? "indeterminate" : "determinate"}
            value={item.status === "COMPLETED" ? 100 : 0}
            color={item.status === "FAILED" ? "error" : "primary"}
          />
          <Typography variant="caption" color="text.secondary">
            Свечей: {item.ingested.toLocaleString("ru-RU")} · запросов: {item.requests}
          </Typography>
          {item.error && <Typography variant="caption" color="error.main" sx={{ display: "block" }}>{item.error}</Typography>}
        </Paper>)}
      </Stack>
    </Stack>}
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 1, mt: 2 }}>
      {(dataset?.timeframes ?? []).map((item) => <Chip key={item.timeframe} variant="outlined"
        label={`${item.timeframe}: ${item.candles.toLocaleString("ru-RU")} · ${formatDate(item.from_timestamp)} — ${formatDate(item.to_timestamp)}`}
        onDelete={canManage ? () => void removeTimeframe(item.timeframe) : undefined} />)}
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
  </Paper>;
}
