"use client";

import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { LearningModelsResponse } from "../../lib/types";

export default function LearningPage() {
  const resource = useApiResource<LearningModelsResponse>("/api/v1/learning/learning/models");
  const { roles } = useAuth();
  const [isTraining, setIsTraining] = useState(false);
  const [trainingError, setTrainingError] = useState("");
  const models = resource.data?.models ?? [];
  const canTrain = roles.includes("admin");

  const train = async () => {
    setIsTraining(true);
    setTrainingError("");
    try {
      await api("/api/v1/learning/learning/train", { method: "POST", body: "{}" });
      resource.reload();
    } catch (reason) {
      setTrainingError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsTraining(false);
    }
  };

  return <SectionPage
    title="Обучение"
    description="Версии адаптивных моделей и обучающие выборки."
    {...resource}
    error={trainingError || resource.error}
    onReload={resource.reload}
  >
    <Stack direction="row" sx={{ mb: 2, justifyContent: "flex-end" }}>
      <Button variant="contained" disabled={!canTrain || isTraining} onClick={() => void train()}>
        {isTraining ? "Обучаем…" : "Запустить обучение"}
      </Button>
    </Stack>
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
