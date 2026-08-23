import { Grid, Paper, Typography } from "@mui/material";
import { formatMoney, formatSignedMoney } from "../../lib/formatters";
import type { Portfolio } from "../../lib/types";

interface MetricCardProps { label: string; value: string; accent?: boolean; positive?: boolean }

function MetricCard({ label, value, accent = false, positive = false }: MetricCardProps) {
  return (
    <Paper variant="outlined" sx={{ borderTop: accent ? 2 : 1, borderTopColor: accent ? "primary.main" : "divider", p: 2.75 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{label}</Typography>
      <Typography component="strong" variant="h5" color={positive ? "success.main" : "text.primary"} sx={{ display: "inline-block", mt: 2 }}>
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary" sx={{ ml: 1 }}>USDT</Typography>
    </Paper>
  );
}

export function MetricsGrid({ portfolio }: { portfolio?: Portfolio }) {
  return (
    <Grid container spacing={1.5} sx={{ mb: 1.5 }}>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}><MetricCard label="Общий капитал" value={formatMoney(portfolio?.total_equity)} accent /></Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}>
        <MetricCard
          label="PnL сегодня"
          value={formatSignedMoney(portfolio?.realized_pnl_today)}
          positive={(portfolio?.realized_pnl_today ?? 0) >= 0}
        />
      </Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}><MetricCard label="Нереализованный PnL" value={formatSignedMoney(portfolio?.unrealized_pnl)} /></Grid>
      <Grid size={{ xs: 12, sm: 6, lg: 3 }}><MetricCard label="Доступно" value={formatMoney(portfolio?.available_balance)} /></Grid>
    </Grid>
  );
}
