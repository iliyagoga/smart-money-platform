import { Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Typography } from "@mui/material";
import { usePagination } from "../../hooks/usePagination";
import type { TradeAnalysisResponse } from "../../lib/types";
import { formatSignedMoney } from "../../lib/formatters";
import { EmptyState } from "../ui/EmptyState";

const number = (value?: number, suffix = "") => value == null ? "—" : `${value.toFixed(2)}${suffix}`;
const duration = (seconds: number) => seconds < 3600 ? `${Math.round(seconds / 60)} мин` : `${(seconds / 3600).toFixed(1)} ч`;

export function TradeAnalyzer({ analysis }: { analysis?: TradeAnalysisResponse }) {
  const metrics = analysis?.metrics;
  const points = analysis?.entry_points ?? [];
  const pagination = usePagination(points);
  const cards = [
    ["Чистый PnL", formatSignedMoney(metrics?.net_pnl)], ["Матожидание", formatSignedMoney(metrics?.expectancy)],
    ["Payoff ratio", number(metrics?.payoff_ratio)], ["Средний R", number(metrics?.average_r, "R")],
    ["Среднее удержание", duration(metrics?.average_duration_seconds ?? 0)], ["Win rate", number(metrics?.win_rate, "%")],
  ];
  return <Paper variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
    <Typography variant="h6" sx={{ px: 1, pb: 2 }}>Анализ сделок и точек входа</Typography>
    <Grid container spacing={1}>{cards.map(([label, value]) => <Grid key={label} size={{ xs: 6, md: 4, xl: 2 }}>
      <Paper variant="outlined" sx={{ p: 1.5, height: "100%" }}><Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h6" sx={{ mt: .5 }}>{value}</Typography></Paper>
    </Grid>)}</Grid>
    <Typography variant="subtitle1" sx={{ px: 1, pt: 3, pb: 1 }}>Качество точек входа</Typography>
    {points.length === 0 ? <EmptyState text="Для анализа нужны закрытые сделки" /> : <TableContainer><Table size="small">
      <TableHead><TableRow><TableCell>Актив</TableCell><TableCell>Направление</TableCell><TableCell>Вход / стоп</TableCell>
        <TableCell>Результат</TableCell><TableCell>R</TableCell><TableCell>Захват движения</TableCell>
        <TableCell>Удержание</TableCell></TableRow></TableHead>
      <TableBody>{pagination.visible.map((point) => <TableRow hover key={point.position_id}><TableCell>{point.symbol}</TableCell>
        <TableCell sx={{ color: point.direction === "LONG" ? "success.main" : "error.main" }}>{point.direction}</TableCell>
        <TableCell>{point.entry_price} / {point.initial_stop_loss_price ?? "—"}</TableCell>
        <TableCell sx={{ color: point.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{formatSignedMoney(point.pnl)} ({number(point.pnl_percent, "%")})</TableCell>
        <TableCell>{number(point.r_multiple, "R")}</TableCell><TableCell>{number(point.capture_rate, "%")}</TableCell>
        <TableCell>{duration(point.duration_seconds)}</TableCell></TableRow>)}</TableBody>
    </Table></TableContainer>}
    {points.length > 0 && <TablePagination component="div" {...pagination.paginationProps} />}
  </Paper>;
}
