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
  id: "NEW_TEMPLATE",
  name: "Новый сценарий",
  version: 1,
  required_objects: [{ kind: "ORDER_BLOCK", active: true, same_direction: true, min_strength: 0.5 }],
  relations: [],
  allowed_timeframes: ["M15", "H1", "H4"],
  direction_source: "ORDER_BLOCK",
  entry_rule: "ORDER_BLOCK",
  stop_rule: "ORDER_BLOCK_EDGE",
  stop_atr_buffer: 0.1,
  target_rule: "FIXED_RR",
  risk_reward: [2, 3],
  ttl_minutes: 1440,
  base_confidence: 0.5,
  overlap_bonus: 0.1,
  strength_weight: 0.1,
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

  const remove = async (templateId: string) => {
    if (!window.confirm(`Удалить шаблон ${templateId}?`)) return;
    try {
      await api(`/api/v1/smc/scenario-templates/${templateId}`, { method: "DELETE" });
      resource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return <Paper variant="outlined" sx={{ p: 3, mt: 2 }}>
    <Stack direction="row" spacing={2} sx={{ alignItems: "center", justifyContent: "space-between" }}>
      <div>
        <Typography variant="h6">JSON-шаблоны сценариев</Typography>
        <Typography variant="body2" color="text.secondary">Scenario Manager перечитывает эти файлы при каждом анализе.</Typography>
      </div>
      <Button variant="contained" disabled={!canManage} onClick={create}>Добавить шаблон</Button>
    </Stack>
    {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    <Stack spacing={1} sx={{ mt: 2 }}>
      {(resource.data?.templates ?? []).map((template) => <Paper key={template.id} variant="outlined" sx={{ p: 2 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ alignItems: { sm: "center" } }}>
          <Typography sx={{ flex: 1 }}>{template.name} · {template.id} · v{template.version}</Typography>
          <Button disabled={!canManage} onClick={() => edit(template)}>JSON</Button>
          <Button color="error" disabled={!canManage} onClick={() => void remove(template.id)}>Удалить</Button>
        </Stack>
      </Paper>)}
    </Stack>
    <Dialog open={Boolean(editor)} onClose={close} fullWidth maxWidth="md">
      <DialogTitle>Редактор JSON-шаблона</DialogTitle>
      <DialogContent>
        <TextField multiline minRows={22} fullWidth value={editor} onChange={(event) => setEditor(event.target.value)}
          sx={{ mt: 1, fontFamily: "monospace" }} />
      </DialogContent>
      <DialogActions><Button onClick={close}>Отмена</Button><Button variant="contained" onClick={() => void save()}>Сохранить</Button></DialogActions>
    </Dialog>
  </Paper>;
}
