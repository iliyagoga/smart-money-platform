"use client";

import { Button, Chip, Grid, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { ScenariosResponse } from "../../lib/types";

export default function ScenariosPage() {
  const resource = useApiResource<ScenariosResponse>("/api/v1/smc/scenarios");
  const { roles } = useAuth();
  const [actionError, setActionError] = useState("");
  const [pendingId, setPendingId] = useState("");
  const scenarios = resource.data?.scenarios ?? [];
  const canRecalculate = roles.some((role) => role === "trader" || role === "admin");

  const recalculate = async (scenarioId: string) => {
    setPendingId(scenarioId);
    setActionError("");
    try {
      await api(`/api/v1/smc/scenarios/${scenarioId}/recalculate`, { method: "POST" });
      resource.reload();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setPendingId("");
    }
  };
  return (
    <SectionPage
      title="Сценарии"
      description="Активные торговые гипотезы SMC."
      {...resource}
      error={actionError || resource.error}
      onReload={resource.reload}
    >
      {scenarios.length === 0 ? <EmptyState text="Активных сценариев нет" /> : <Grid container spacing={2}>{scenarios.map((scenario) => (
        <Grid key={scenario.id} size={{ xs: 12, md: 6, xl: 4 }}><Paper variant="outlined" sx={{ p: 3, height: "100%" }}>
          <Stack direction="row" sx={{ justifyContent: "space-between" }}>
            <Typography variant="h6">{scenario.symbol}</Typography>
            <Chip label={scenario.status} size="small" />
          </Stack>
          <Typography color="text.secondary" sx={{ my: 1 }}>{scenario.setup_type} · {scenario.timeframe}</Typography>
          <Typography color={scenario.direction.includes("BULL") ? "success.main" : "error.main"}>{scenario.direction}</Typography>
          <Stack spacing={0.5} sx={{ mt: 2 }}>
            <Typography variant="body2">Вход: {scenario.entry_zone_low} — {scenario.entry_zone_high}</Typography>
            <Typography variant="body2" color="error.main">Stop Loss: {scenario.stop_loss_price}</Typography>
            <Typography variant="body2" color="success.main">Take Profit: {scenario.take_profit_prices.join(" · ")}</Typography>
          </Stack>
          <Typography variant="h4" sx={{ mt: 3 }}>{Math.round(scenario.confidence * 100)}%</Typography>
          <Typography variant="caption" color="text.secondary">Уверенность сценария</Typography>
          <Button
            variant="outlined"
            disabled={!canRecalculate || pendingId === scenario.id}
            onClick={() => void recalculate(scenario.id)}
            fullWidth
            sx={{ mt: 2 }}
          >
            {pendingId === scenario.id ? "Пересчитываем…" : "Пересчитать"}
          </Button>
        </Paper></Grid>
      ))}</Grid>}
    </SectionPage>
  );
}
