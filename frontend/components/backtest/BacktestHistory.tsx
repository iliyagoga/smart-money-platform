import { Button, Checkbox, Chip, CircularProgress, LinearProgress, Paper, Stack, TablePagination, TextField, Typography } from "@mui/material";
import { useState } from "react";
import type { BacktestRunSummary } from "../../lib/backtest/apiTypes";

interface BacktestHistoryProps {
  onCopy: (run: BacktestRunSummary) => void;
  onDeletePeriod: (from: string, to: string) => Promise<number | undefined>;
  onDelete: (runs: BacktestRunSummary[]) => void;
  onExport: (run: BacktestRunSummary, format: "csv" | "json") => void;
  onOpen: (run: BacktestRunSummary) => void;
  onRepeat: (run: BacktestRunSummary) => void;
  onSaveConfiguration: (run: BacktestRunSummary) => void;
  onCompare: (ids: string[]) => void;
  busy: boolean;
  loading: boolean;
  onPageChange: (page: number) => void;
  onRowsPerPageChange: (rows: number) => void;
  page: number;
  rowsPerPage: number;
  runs: BacktestRunSummary[];
  total: number;
}

const statusColor = (status: BacktestRunSummary["status"]) => {
  if (status === "COMPLETED") return "success";
  if (status === "FAILED") return "error";
  return "default";
};

export function BacktestHistory({ busy, loading, onCompare, onCopy, onDelete, onDeletePeriod, onExport, onOpen, onPageChange,
  onRepeat, onSaveConfiguration, onRowsPerPageChange, page, rowsPerPage, runs, total }: BacktestHistoryProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [deletedCount, setDeletedCount] = useState<number>();
  const invalidPeriod = Boolean(dateFrom && dateTo && dateFrom > dateTo);
  const pageRuns = runs;
  const selectedRuns = runs.filter((run) => selected.includes(run.id));
  const comparableIds = selectedRuns.filter((run) => run.status === "COMPLETED").map((run) => run.id);
  const pageIds = pageRuns.map((run) => run.id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.includes(id));
  return <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
    <Stack direction={{ xs: "column", md: "row" }} sx={{ alignItems: { md: "center" }, justifyContent: "space-between", mb: 2, gap: 1 }}>
      <Typography variant="h6">Сохранённые запуски</Typography>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
        <Button disabled={busy || comparableIds.length < 2} onClick={() => onCompare(comparableIds)}>Сравнить ({comparableIds.length})</Button>
        <Button color="error" disabled={busy || !selectedRuns.length} onClick={() => onDelete(selectedRuns)}>
          Удалить выбранные ({selectedRuns.length})
        </Button>
        {busy && <CircularProgress size={22} />}
      </Stack>
    </Stack>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 1, alignItems: { sm: "center" } }}>
      <TextField label="Дата создания: с" type="date" size="small" value={dateFrom} disabled={busy}
        slotProps={{ inputLabel: { shrink: true } }}
        onChange={(event) => { setDateFrom(event.target.value); setDeletedCount(undefined); }} />
      <TextField label="По включительно" type="date" size="small" value={dateTo} disabled={busy}
        error={invalidPeriod} helperText={invalidPeriod ? "Конец периода раньше начала" : undefined}
        slotProps={{ inputLabel: { shrink: true } }}
        onChange={(event) => { setDateTo(event.target.value); setDeletedCount(undefined); }} />
      <Button color="error" variant="outlined" disabled={busy || !dateFrom || !dateTo || invalidPeriod}
        onClick={async () => {
          setDeletedCount(undefined);
          const count = await onDeletePeriod(dateFrom, dateTo);
          if (count !== undefined) { setSelected([]); setDeletedCount(count); }
        }}>Удалить все за период</Button>
    </Stack>
    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
      По дате создания, на всех страницах. Даты указаны в вашем часовом поясе. Активные запуски сохраняются.
    </Typography>
    {deletedCount !== undefined && <Typography role="status" sx={{ mb: 1 }}>Удалено отчётов: {deletedCount}</Typography>}
    {loading && <LinearProgress sx={{ mb: 1 }} />}
    <Stack direction="row" sx={{ alignItems: "center", mb: 1 }}>
      <Checkbox checked={allPageSelected} indeterminate={!allPageSelected && pageIds.some((id) => selected.includes(id))}
        onChange={(event) => setSelected((current) => event.target.checked
          ? Array.from(new Set([...current, ...pageIds]))
          : current.filter((id) => !pageIds.includes(id)))} />
      <Typography variant="body2" color="text.secondary">Выбрать страницу</Typography>
    </Stack>
    <Stack spacing={1}>{pageRuns.map((run) => <Stack
      key={run.id}
      direction={{ xs: "column", md: "row" }}
      sx={{ alignItems: { md: "center" }, borderBottom: 1, borderColor: "divider", py: 1.25, gap: 1 }}
    >
      <Checkbox
        checked={selected.includes(run.id)}
        onChange={(event) => setSelected((current) => event.target.checked
          ? [...current, run.id]
          : current.filter((id) => id !== run.id))}
      />
      <Stack sx={{ flex: 1 }}><Typography sx={{ fontWeight: 650 }}>{run.symbol} · {run.timeframe}</Typography>
        <Typography variant="caption" color="text.secondary">{new Date(run.created_at).toLocaleString("ru-RU")}</Typography>
      </Stack>
      <Chip label={run.status === "RUNNING" ? `${run.progress}%` : run.status} color={statusColor(run.status)} size="small" />
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onOpen(run)}>Открыть</Button>
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onRepeat(run)}>Повторить</Button>
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onCopy(run)}>Копировать конфиг</Button>
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onSaveConfiguration(run)}>Сохранить конфигурацию</Button>
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onExport(run, "csv")}>CSV</Button>
      <Button disabled={busy || run.status !== "COMPLETED"} onClick={() => onExport(run, "json")}>JSON</Button>
      <Button color="error" disabled={busy || run.status === "QUEUED" || run.status === "RUNNING"} onClick={() => onDelete([run])}>Удалить</Button>
    </Stack>)}</Stack>
    <TablePagination component="div" count={total} page={page}
      onPageChange={(_,value) => { setSelected([]); onPageChange(value); }} rowsPerPage={rowsPerPage}
      onRowsPerPageChange={(event) => { setSelected([]); onRowsPerPageChange(Number(event.target.value)); }}
      rowsPerPageOptions={[5,10,25,50]} labelRowsPerPage="Запусков на странице" />
  </Paper>;
}
