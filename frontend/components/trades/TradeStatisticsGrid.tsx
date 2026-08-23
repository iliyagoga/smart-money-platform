import { Grid, Paper, Typography } from "@mui/material";
import type { TradeStatistics } from "../../lib/types";

interface StatProps { label: string; value: string }

function Stat({ label, value }: StatProps) {
  return <Paper variant="outlined" sx={{ p: 2.5 }}><Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography variant="h5" sx={{ mt: 1 }}>{value}</Typography>
  </Paper>;
}

export function TradeStatisticsGrid({ statistics }: { statistics?: TradeStatistics }) {
  return <Grid container spacing={1.5}>
    <Grid size={{ xs: 6, lg: 3 }}><Stat label="Всего сделок" value={String(statistics?.total_trades ?? 0)} /></Grid>
    <Grid size={{ xs: 6, lg: 3 }}><Stat label="Win rate" value={`${(statistics?.win_rate ?? 0).toFixed(1)}%`} /></Grid>
    <Grid size={{ xs: 6, lg: 3 }}><Stat label="Profit factor" value={statistics?.profit_factor?.toFixed(2) ?? "—"} /></Grid>
    <Grid size={{ xs: 6, lg: 3 }}><Stat label="Max drawdown" value={(statistics?.max_drawdown ?? 0).toFixed(2)} /></Grid>
  </Grid>;
}
