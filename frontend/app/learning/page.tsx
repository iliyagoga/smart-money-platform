"use client";

import { Chip, Paper, Stack, Typography } from "@mui/material";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import type { LearningModelsResponse } from "../../lib/types";

export default function LearningPage() {
  const resource = useApiResource<LearningModelsResponse>("/api/v1/learning/learning/models");
  const models = resource.data?.models ?? [];
  return <SectionPage title="Обучение" description="Версии адаптивных моделей и обучающие выборки." {...resource} onReload={resource.reload}>
    {models.length === 0 ? <EmptyState text="Обученные модели пока отсутствуют" /> : <Stack spacing={1.5}>{models.map((model) => (
      <Paper key={model.id} variant="outlined" sx={{ p: 2.5 }}>
        <Stack direction={{ xs: "column", sm: "row" }} sx={{ justifyContent: "space-between", gap: 1 }}>
        <Stack><Typography sx={{ fontWeight: 700 }}>{model.type} · {model.version}</Typography>
          <Typography variant="caption" color="text.secondary">Образцов: {model.samples_count}</Typography>
        </Stack>
        <Chip label={model.is_active ? "Активна" : "Архив"} color={model.is_active ? "success" : "default"} size="small" />
        </Stack>
      </Paper>
    ))}</Stack>}
  </SectionPage>;
}
