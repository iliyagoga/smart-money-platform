"use client";

import { Button, Checkbox, FormControl, FormControlLabel, InputLabel, ListItemText, MenuItem, Paper, Select, Stack, Switch, TextField, Typography } from "@mui/material";
import type { BacktestSettings, DirectionMode } from "../../lib/backtest/types";

interface Props { isRunning: boolean; onChange: (settings: BacktestSettings) => void; onRun: () => void; progress: number;
  testsCompleted: number; testsTotal: number; progressStage?: string; settings: BacktestSettings; templates: Array<{ id: string; name: string }> }
type BoundKey = keyof BacktestSettings["optimizationBounds"];

export function BacktestSettingsForm({ isRunning, onChange, onRun, progress, progressStage, settings, templates, testsCompleted, testsTotal }: Props) {
  const updateNumber = (key: keyof BacktestSettings, value: string) => onChange({ ...settings, [key]: Number(value) });
  const updateBound = (key: BoundKey, side: "minimum" | "maximum", value: string) => onChange({
    ...settings, optimizationBounds: { ...settings.optimizationBounds,
      [key]: { ...settings.optimizationBounds[key], [side]: value === "" ? undefined : Number(value) } },
  });
  const limits: Record<BoundKey, [number, number]> = {
    minimumObStrength: [0, 1], minimumImpulseAtr: [0, 20], minimumVolumeRatio: [0, 100],
    minimumAdx: [0, 100], stopBufferAtr: [0, 10],
  };
  const boundsValid = Object.entries(settings.optimizationBounds).every(([name, bounds]) =>
    (bounds.minimum === undefined && bounds.maximum === undefined)
    || (bounds.minimum !== undefined && bounds.maximum !== undefined && bounds.minimum <= bounds.maximum
      && bounds.minimum >= limits[name as BoundKey][0] && bounds.maximum <= limits[name as BoundKey][1]));
  const isValid = settings.initialCapital > 0 && settings.positionSizePercent > 0 && settings.positionSizePercent <= 100
    && settings.riskPerTradePercent > 0 && settings.templateIds.length > 0
    && (!settings.autoOptimize || (settings.templateIds.includes("DEMO_SMC_V1") && boundsValid));
  const boundary = (key: BoundKey, label: string) => <Stack direction="row" spacing={1}>
    <TextField fullWidth label={`${label}: от`} type="number" value={settings.optimizationBounds[key].minimum ?? ""}
      placeholder={`авто · минимум ${limits[key][0]}`} slotProps={{ htmlInput: { min: limits[key][0], max: limits[key][1] } }}
      onChange={(event) => updateBound(key, "minimum", event.target.value)} />
    <TextField fullWidth label={`${label}: до`} type="number" value={settings.optimizationBounds[key].maximum ?? ""}
      placeholder={`авто · максимум ${limits[key][1]}`} slotProps={{ htmlInput: { min: limits[key][0], max: limits[key][1] } }}
      onChange={(event) => updateBound(key, "maximum", event.target.value)} />
  </Stack>;

  return <Paper variant="outlined" sx={{ p: 3 }}><Typography variant="h6">Параметры бэктеста</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: .5, mb: 2.5 }}>
      Параметры SMC подбираются автоматически. Здесь задаются только исполнение и необязательные границы поиска.
    </Typography><Stack spacing={2}>
      <TextField label="Стратегия" value="Smart Money Concept" disabled />
      <TextField select label="Направление" value={settings.directionMode}
        onChange={(event) => onChange({ ...settings, directionMode: event.target.value as DirectionMode })}>
        <MenuItem value="BOTH">Long и Short</MenuItem><MenuItem value="LONG">Только Long</MenuItem><MenuItem value="SHORT">Только Short</MenuItem>
      </TextField>
      <FormControl fullWidth><InputLabel id="backtest-templates-label">Шаблоны для теста</InputLabel>
        <Select labelId="backtest-templates-label" multiple label="Шаблоны для теста" value={settings.templateIds}
          onChange={(event) => onChange({ ...settings, templateIds: typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value })}
          renderValue={(selected) => `Выбрано: ${selected.length}`}>
          {templates.map((template) => <MenuItem key={template.id} value={template.id}>
            <Checkbox checked={settings.templateIds.includes(template.id)} /><ListItemText primary={template.name} secondary={template.id} />
          </MenuItem>)}
        </Select>
      </FormControl>
      <FormControlLabel control={<Switch checked={settings.autoOptimize} onChange={(_, value) => onChange({ ...settings, autoOptimize: value })} />}
        label="Автоматический подбор на периоде оптимизации" />
      {settings.autoOptimize && <Paper variant="outlined" sx={{ p: 2 }}><Typography variant="subtitle2">Необязательные границы перебора</Typography>
        <Typography variant="caption" color="text.secondary">Оставьте пустыми для автоматических диапазонов. Заполняйте сразу обе границы параметра.</Typography>
        <Stack spacing={1.5} sx={{ mt: 1.5 }}>
          {boundary("minimumObStrength", "Сила OB")}{boundary("minimumImpulseAtr", "Импульс, ATR")}
          {boundary("minimumVolumeRatio", "Отношение объёма")}{boundary("minimumAdx", "Минимальный ADX")}
          {boundary("stopBufferAtr", "Буфер стопа, ATR")}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField fullWidth label="Максимум прогонов" type="number" value={settings.optimizationMaxCombinations} onChange={(e) => updateNumber("optimizationMaxCombinations",e.target.value)} />
            <TextField fullWidth label="На валидацию" type="number" value={settings.optimizationValidationCandidates} onChange={(e) => updateNumber("optimizationValidationCandidates",e.target.value)} />
            <TextField fullWidth label="Минимум сделок" type="number" value={settings.optimizationMinimumTrades} onChange={(e) => updateNumber("optimizationMinimumTrades",e.target.value)} />
            <TextField fullWidth label="Штраф просадки" type="number" value={settings.optimizationDrawdownPenalty} onChange={(e) => updateNumber("optimizationDrawdownPenalty",e.target.value)} />
          </Stack>
        </Stack></Paper>}
      <Typography variant="subtitle2">Исполнение и риск</Typography>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <TextField fullWidth label="Капитал" value={settings.initialCapital} type="number" onChange={(e) => updateNumber("initialCapital",e.target.value)} />
        <TextField fullWidth label="Позиция, %" value={settings.positionSizePercent} type="number" onChange={(e) => updateNumber("positionSizePercent",e.target.value)} />
        <TextField fullWidth label="Риск, %" value={settings.riskPerTradePercent} type="number" onChange={(e) => updateNumber("riskPerTradePercent",e.target.value)} />
        <TextField fullWidth label="Плечо" value={settings.leverage} type="number" onChange={(e) => updateNumber("leverage",e.target.value)} />
      </Stack>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <TextField fullWidth label="Maker, %" value={settings.makerFeePercent} type="number" onChange={(e) => updateNumber("makerFeePercent",e.target.value)} />
        <TextField fullWidth label="Taker, %" value={settings.takerFeePercent} type="number" onChange={(e) => updateNumber("takerFeePercent",e.target.value)} />
        <TextField fullWidth label="Проскальзывание, %" value={settings.slippagePercent} type="number" onChange={(e) => updateNumber("slippagePercent",e.target.value)} />
        <TextField fullWidth label="Доля объёма, %" value={settings.volumeParticipationPercent} type="number" onChange={(e) => updateNumber("volumeParticipationPercent",e.target.value)} />
      </Stack>
      <Button variant="contained" size="large" disabled={!isValid || isRunning} onClick={onRun}>
        {isRunning ? (testsTotal ? `${progressStage === "VALIDATION" ? "Валидация" : "Оптимизация"}: ${testsCompleted} / ${testsTotal}`
          : `Подготовка данных… ${progress}%`) : settings.autoOptimize ? "Подобрать и проверить" : "Запустить бэктест"}
      </Button>
      {!isValid && <Typography variant="caption" color="error.main">Проверьте границы, риск и выбранный шаблон.</Typography>}
    </Stack></Paper>;
}
