"use client";

import { Alert, Button, LinearProgress, MenuItem, Paper, Slider, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { BacktestRun, BacktestRunsResponse, BackendBacktestResult } from "../../lib/backtest/apiTypes";

interface ReplayEvent { detail: string; timestamp: number; type: string }

function eventsFrom(result?: BackendBacktestResult): ReplayEvent[] {
  if (!result) return [];
  const trades = result.trades.flatMap((trade) => [
    { detail: `${trade.direction} @ ${trade.entry_price}`, timestamp: trade.entry_time, type: "Вход" },
    { detail: `${trade.reason}, PnL ${trade.pnl.toFixed(2)}`, timestamp: trade.exit_time, type: "Выход" },
  ]);
  return trades.sort((left, right) => left.timestamp - right.timestamp);
}

export default function ReplayPage() {
  const runs = useApiResource<BacktestRunsResponse>("/api/v1/backtest/backtests?limit=100");
  const completed = (runs.data?.runs ?? []).filter((item) => item.status === "COMPLETED");
  const [runId, setRunId] = useState("");
  const [result, setResult] = useState<BackendBacktestResult>();
  const [position, setPosition] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const events = useMemo(() => eventsFrom(result), [result]);

  useEffect(() => {
    if (!playing || position >= events.length - 1) return;
    const timer = window.setInterval(() => setPosition((value) => Math.min(value + 1, events.length - 1)), 500);
    return () => window.clearInterval(timer);
  }, [events.length, playing, position]);

  const load = async (id: string) => {
    setRunId(id);
    setPlaying(false);
    setPosition(0);
    try {
      const run = await api<BacktestRun>(`/api/v1/backtest/backtests/${id}`);
      setResult(run.result);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  const visible = events.slice(Math.max(0, position - 12), position + 1).reverse();
  return <SectionPage title="Replay" description="Пошаговое воспроизведение решений и виртуальных сделок завершённого бэктеста.">
    {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
    <Paper variant="outlined" sx={{ p: 3 }}>
      <TextField select fullWidth label="Запуск" value={runId} onChange={(event) => void load(event.target.value)}>
        {completed.map((run) => <MenuItem key={run.id} value={run.id}>
          {run.symbol} · {run.timeframe} · {new Date(run.created_at).toLocaleString("ru-RU")}
        </MenuItem>)}
      </TextField>
      {result && <Stack spacing={2.5} sx={{ mt: 3 }}>
        <LinearProgress variant="determinate" value={events.length ? (position + 1) / events.length * 100 : 0} />
        <Slider min={0} max={Math.max(0, events.length - 1)} value={position}
          onChange={(_, value) => setPosition(value as number)} aria-label="Позиция Replay" />
        <Stack direction="row" spacing={1}>
          <Button variant="contained" disabled={!events.length} onClick={() => setPlaying((value) => !value)}>
            {playing ? "Пауза" : "Воспроизвести"}
          </Button>
          <Button disabled={position === 0} onClick={() => setPosition((value) => value - 1)}>Назад</Button>
          <Button disabled={position >= events.length - 1} onClick={() => setPosition((value) => value + 1)}>Шаг</Button>
        </Stack>
        <Typography variant="h6">Журнал событий</Typography>
        {visible.map((event, index) => <Paper key={`${event.timestamp}-${event.type}-${index}`} variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="caption" color="text.secondary">
            {new Date(event.timestamp).toLocaleString("ru-RU")} · {event.type}
          </Typography>
          <Typography>{event.detail}</Typography>
        </Paper>)}
      </Stack>}
    </Paper>
  </SectionPage>;
}
