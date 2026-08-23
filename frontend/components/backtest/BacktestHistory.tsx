import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import type { BacktestRunSummary } from "../../lib/backtest/apiTypes";

interface BacktestHistoryProps {
  onExport: (run: BacktestRunSummary, format: "csv" | "json") => void;
  onOpen: (run: BacktestRunSummary) => void;
  runs: BacktestRunSummary[];
}

const statusColor = (status: BacktestRunSummary["status"]) => {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED") return "error";
  return "default";
};

export function BacktestHistory({ onExport, onOpen, runs }: BacktestHistoryProps) {
  return <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
    <Typography variant="h6" sx={{ mb: 2 }}>Сохранённые запуски</Typography>
    <Stack spacing={1}>{runs.map((run) => <Stack
      key={run.id}
      direction={{ xs: "column", md: "row" }}
      sx={{ alignItems: { md: "center" }, borderBottom: 1, borderColor: "divider", py: 1.25, gap: 1 }}
    >
      <Stack sx={{ flex: 1 }}><Typography sx={{ fontWeight: 650 }}>{run.symbol} · {run.timeframe}</Typography>
        <Typography variant="caption" color="text.secondary">{new Date(run.created_at).toLocaleString("ru-RU")}</Typography>
      </Stack>
      <Chip label={run.status === "RUNNING" ? `${run.progress}%` : run.status} color={statusColor(run.status)} size="small" />
      <Button disabled={run.status !== "COMPLETED"} onClick={() => onOpen(run)}>Открыть</Button>
      <Button disabled={run.status !== "COMPLETED"} onClick={() => onExport(run, "csv")}>CSV</Button>
      <Button disabled={run.status !== "COMPLETED"} onClick={() => onExport(run, "json")}>JSON</Button>
    </Stack>)}</Stack>
  </Paper>;
}
