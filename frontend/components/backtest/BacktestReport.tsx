import { Chip, Grid, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import type { BacktestResult } from "../../lib/backtest/types";
import { EquityChart } from "./EquityChart";

interface MetricProps { label: string; value: string; tone?: "success" | "error" }

function Metric({ label, tone, value }: MetricProps) {
  return <Paper variant="outlined" sx={{ p: 2.5 }}>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography variant="h5" color={tone ? `${tone}.main` : "text.primary"} sx={{ mt: 1 }}>{value}</Typography>
  </Paper>;
}

export function BacktestReport({ result }: { result: BacktestResult }) {
  const profitTone = result.netProfit >= 0 ? "success" : "error";
  return <>
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Итоговый капитал" value={result.finalCapital.toFixed(2)} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Доходность" value={`${result.totalReturnPercent.toFixed(2)}%`} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Макс. просадка" value={`${result.maxDrawdownPercent.toFixed(2)}%`} tone="error" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Win rate" value={`${result.winRate.toFixed(1)}%`} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Сделок" value={String(result.totalTrades)} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Profit factor" value={result.profitFactor?.toFixed(2) ?? "—"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Средняя сделка" value={result.averageTrade.toFixed(2)} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Чистый PnL" value={result.netProfit.toFixed(2)} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Sharpe ratio" value={result.sharpeRatio?.toFixed(2) ?? "—"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}>
        <Metric label="Buy & hold" value={`${(result.benchmarkReturnPercent ?? 0).toFixed(2)}%`} />
      </Grid>
    </Grid>
    <EquityChart points={result.equity} />
    <Paper variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
      <Typography variant="h6" sx={{ px: 1, pb: 2 }}>Журнал сделок</Typography>
      <TableContainer><Table size="small">
        <TableHead><TableRow><TableCell>#</TableCell><TableCell>Вход</TableCell><TableCell>Выход</TableCell><TableCell>Сторона</TableCell>
          <TableCell>Цена входа</TableCell><TableCell>Цена выхода</TableCell><TableCell>PnL</TableCell><TableCell>Причина</TableCell>
        </TableRow></TableHead>
        <TableBody>{result.trades.map((trade) => <TableRow key={trade.id}>
          <TableCell>{trade.id}</TableCell><TableCell>{new Date(trade.entryTime).toLocaleString("ru-RU")}</TableCell>
          <TableCell>{new Date(trade.exitTime).toLocaleString("ru-RU")}</TableCell><TableCell>{trade.direction}</TableCell>
          <TableCell>{trade.entryPrice.toFixed(2)}</TableCell><TableCell>{trade.exitPrice.toFixed(2)}</TableCell>
          <TableCell sx={{ color: trade.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{trade.pnl.toFixed(2)}</TableCell>
          <TableCell><Chip size="small" label={trade.reason} variant="outlined" /></TableCell>
        </TableRow>)}</TableBody>
      </Table></TableContainer>
    </Paper>
  </>;
}
