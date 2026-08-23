"use client";

import { Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import type { ScenariosResponse } from "../../lib/types";

export default function ScenariosPage() {
  const resource = useApiResource<ScenariosResponse>("/api/v1/smc/scenarios");
  const scenarios = resource.data?.scenarios ?? [];
  return (
    <SectionPage title="Сценарии" description="Активные торговые гипотезы SMC." {...resource} onReload={resource.reload}>
      {scenarios.length === 0 ? <EmptyState text="Активных сценариев нет" /> : <Grid container spacing={2}>{scenarios.map((scenario) => (
        <Grid key={scenario.id} size={{ xs: 12, md: 6, xl: 4 }}><Paper variant="outlined" sx={{ p: 3, height: "100%" }}>
          <Stack direction="row" sx={{ justifyContent: "space-between" }}>
            <Typography variant="h6">{scenario.symbol}</Typography>
            <Chip label={scenario.status} size="small" />
          </Stack>
          <Typography color="text.secondary" sx={{ my: 1 }}>{scenario.setup_type} · {scenario.timeframe}</Typography>
          <Typography color={scenario.direction.includes("BULL") ? "success.main" : "error.main"}>{scenario.direction}</Typography>
          <Typography variant="h4" sx={{ mt: 3 }}>{Math.round(scenario.confidence * 100)}%</Typography>
          <Typography variant="caption" color="text.secondary">Уверенность сценария</Typography>
        </Paper></Grid>
      ))}</Grid>}
    </SectionPage>
  );
}
