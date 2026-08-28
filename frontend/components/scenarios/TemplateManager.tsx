"use client";

import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Paper, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";

interface ScenarioTemplate {
  id: string;
  name: string;
  version: number;
  [key: string]: unknown;
}

interface TemplatesResponse {
  templates: ScenarioTemplate[];
  total: number;
}

const starterTemplate = {
  id: "NEW_CONFIG",
  name: "Новая конфигурация алгоритма",
  version: 1,
  enabled: true,
  execution_timeframes: ["M1", "M5", "M15"],
  allowed_directions: ["LONG", "SHORT"],
  avoid_countertrend_entries: true,
  entry_source: "ORDER_BLOCK",
  ob_entry_mode: "MIDPOINT",
  ob_boundary_mode: "FULL",
  ob_mitigation_mode: "CLOSE_INSIDE",
  minimum_ob_strength: 0.45,
  minimum_impulse_atr: 1,
  volume_period: 20,
  minimum_volume_ratio: 0.8,
  adx_period: 14,
  minimum_adx: 18,
  stop_buffer_atr: 0.1,
  risk_reward: [2, 3],
  minimum_rr: 1.5,
  entry_valid_for_bars: 30,
  one_trade_per_zone: true,
  target_allocations: [0.5, 0.5],
};

export function TemplateManager({ canManage }: { canManage: boolean }) {
  const resource = useApiResource<TemplatesResponse>("/api/v1/smc/scenario-templates");
  const [editor, setEditor] = useState("");
  const [error, setError] = useState("");

  const edit = (template: ScenarioTemplate) => setEditor(JSON.stringify(template, null, 2));
  const create = () => setEditor(JSON.stringify(starterTemplate, null, 2));
  const close = () => setEditor("");

  const save = async () => {
    try {
      const template = JSON.parse(editor) as ScenarioTemplate;
      await api(`/api/v1/smc/scenario-templates/${template.id}`, {
        method: "PUT",
        body: JSON.stringify(template),
      });
      close();
      resource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
    <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <Typography variant="h6">Конфигурации встроенного алгоритма</Typography>
        <Typography variant="body2" color="text.secondary">JSON задаёт параметры; последовательность расчёта зафиксирована в коде.</Typography>
      </div>
      <Button variant="contained" disabled={!canManage} onClick={create}>Добавить шаблон</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    <Stack spacing={1} sx={{ mt: 2 }}>
      {(resource.data?.templates ?? []).map((template) => <Paper key={template.id} variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
          <Typography sx={{ flex: 1 }}>{template.name} · {template.id} · v{template.version}</Typography>
          <Button disabled={!canManage} onClick={() => edit(template)}>JSON</Button>
        </Stack>
      </Paper>)}
    </Stack>
    <Dialog open={Boolean(editor)} onClose={close} fullWidth maxWidth="md">
      <DialogTitle>Редактор входной конфигурации</DialogTitle>
      <DialogContent>
        <TextField multiline minRows={22} fullWidth value={editor} onChange={(event) => setEditor(event.target.value)}
          sx={{ mt: 1, fontFamily: "monospace" }} />
      </DialogContent>
      <DialogActions><Button onClick={close}>Отмена</Button><Button variant="contained" onClick={() => void save()}>Сохранить</Button></DialogActions>
    </Dialog>
  </Paper>;
}
