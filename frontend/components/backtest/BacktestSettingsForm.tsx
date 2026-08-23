"use client";

import { Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import type { BacktestSettings, DirectionMode } from "../../lib/backtest/types";

interface BacktestSettingsFormProps {
  isRunning: boolean;
  onChange: (settings: BacktestSettings) => void;
  onRun: () => void;
  settings: BacktestSettings;
}

export function BacktestSettingsForm({ isRunning, onChange, onRun, settings }: BacktestSettingsFormProps) {
  const updateNumber = (key: keyof BacktestSettings, value: string) => onChange({ ...settings, [key]: Number(value) });
  const isValid = settings.initialCapital > 0
    && settings.fastPeriod >= 2
    && settings.slowPeriod > settings.fastPeriod
    && settings.positionSizePercent > 0
    && settings.positionSizePercent <= 100;

  return <Paper variant="outlined" sx={{ p: 3 }}>
    <Typography variant="h6">Параметры стратегии</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>Пересечение двух скользящих средних.</Typography>
    <Stack spacing={2}>
      <TextField
        select
        label="Направление"
        value={settings.directionMode}
        onChange={(event) => onChange({ ...settings, directionMode: event.target.value as DirectionMode })}
      >
        <MenuItem value="BOTH">Long и Short</MenuItem><MenuItem value="LONG">Только Long</MenuItem><MenuItem value="SHORT">Только Short</MenuItem>
      </TextField>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Быстрая MA" value={settings.fastPeriod} type="number"
          onChange={(event) => updateNumber("fastPeriod", event.target.value)} />
        <TextField fullWidth label="Медленная MA" value={settings.slowPeriod} type="number"
          onChange={(event) => updateNumber("slowPeriod", event.target.value)} />
      </Stack>
      <TextField label="Начальный капитал" value={settings.initialCapital} type="number"
        onChange={(event) => updateNumber("initialCapital", event.target.value)} />
      <TextField label="Размер позиции, %" value={settings.positionSizePercent} type="number"
        onChange={(event) => updateNumber("positionSizePercent", event.target.value)} />
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Stop Loss, %" value={settings.stopLossPercent} type="number"
          onChange={(event) => updateNumber("stopLossPercent", event.target.value)} />
        <TextField fullWidth label="Take Profit, %" value={settings.takeProfitPercent} type="number"
          onChange={(event) => updateNumber("takeProfitPercent", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Комиссия, %" value={settings.feePercent} type="number"
          onChange={(event) => updateNumber("feePercent", event.target.value)} />
        <TextField fullWidth label="Проскальзывание, %" value={settings.slippagePercent} type="number"
          onChange={(event) => updateNumber("slippagePercent", event.target.value)} />
      </Stack>
      <Button variant="contained" size="large" disabled={!isValid || isRunning} onClick={onRun}>
        {isRunning ? "Выполняем расчёт…" : "Запустить бэктест"}
      </Button>
      {!isValid && <Typography variant="caption" color="error.main">
        Медленная MA должна быть больше быстрой, остальные значения — положительными.
      </Typography>}
    </Stack>
  </Paper>;
}
