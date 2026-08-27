"use client";

import { Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import { useAuth } from "../../components/auth/AuthProvider";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import type { ScenariosResponse } from "../../lib/types";
import { TemplateManager } from "../../components/scenarios/TemplateManager";

export default function ScenariosPage() {
  const resource = useApiResource<ScenariosResponse>("/api/v1/smc/signals");
  const { roles } = useAuth();
  const scenarios = resource.data?.signals ?? [];
  return (
    <SectionPage
      title="Алгоритмические сигналы"
      description="Прямой результат фиксированного SMC-алгоритма."
      {...resource}
      error={resource.error}
      onReload={resource.reload}
    >
      {scenarios.length === 0 ? <EmptyState text="Алгоритмических сигналов нет" /> : <Grid container spacing={2}>{scenarios.map((scenario) => (
        <Grid key={scenario.id} size={{ xs: 12, md: 6, xl: 4 }}><Paper variant="outlined" sx={{ p: 3, height: "100%" }}>
          <Stack direction="row" sx={{ justifyContent: "space-between" }}>
            <Typography variant="h6">{scenario.symbol}</Typography>
            <Chip label="SIGNAL" size="small" />
          </Stack>
          <Typography color="text.secondary" sx={{ my: 1 }}>{scenario.config_id} · {scenario.timeframe}</Typography>
          <Typography color={scenario.direction === "LONG" ? "success.main" : "error.main"}>{scenario.direction}</Typography>
          <Stack spacing={0.5} sx={{ mt: 2 }}>
            <Typography variant="body2">Вход: {scenario.entry_zone_low} — {scenario.entry_zone_high}</Typography>
            <Typography variant="body2" color="error.main">Stop Loss: {scenario.stop_loss_price}</Typography>
            <Typography variant="body2" color="success.main">Take Profit: {scenario.take_profit_prices.join(" · ")}</Typography>
          </Stack>
          <Typography variant="h4" sx={{ mt: 3 }}>{Math.round(scenario.score * 100)}%</Typography>
          <Typography variant="caption" color="text.secondary">Детерминированная оценка качества</Typography>
        </Paper></Grid>
      ))}</Grid>}
      <TemplateManager canManage={roles.includes("admin")} />
    </SectionPage>
  );
}
