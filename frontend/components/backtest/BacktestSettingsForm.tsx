"use client";

import { Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import type { BacktestSettings, DirectionMode } from "../../lib/backtest/types";

interface BacktestSettingsFormProps {
  isRunning: boolean;
  onChange: (settings: BacktestSettings) => void;
  onRun: () => void;
  progress: number;
  settings: BacktestSettings;
}

export function BacktestSettingsForm({ isRunning, onChange, onRun, progress, settings }: BacktestSettingsFormProps) {
  const updateNumber = (key: keyof BacktestSettings, value: string) => onChange({ ...settings, [key]: Number(value) });
  const isValid = settings.initialCapital > 0
    && settings.positionSizePercent > 0
    && settings.positionSizePercent <= 100
    && settings.riskPerTradePercent > 0
    && settings.templateIds.length > 0;

  return <Paper variant="outlined" sx={{ p: 3 }}>
    <Typography variant="h6">Параметры стратегии</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
      Полный SMC-конвейер на сохранённых закрытых свечах.
    </Typography>
    <Stack spacing={2}>
      <TextField label="Стратегия" value="Smart Money Concept" disabled />
      <TextField
        select
        label="Направление"
        value={settings.directionMode}
        onChange={(event) => onChange({ ...settings, directionMode: event.target.value as DirectionMode })}
      >
        <MenuItem value="BOTH">Long и Short</MenuItem><MenuItem value="LONG">Только Long</MenuItem><MenuItem value="SHORT">Только Short</MenuItem>
      </TextField>
      <TextField label="Шаблоны" value={settings.templateIds.join(", ")} helperText="ID JSON-шаблонов через запятую"
        onChange={(event) => onChange({ ...settings, templateIds: event.target.value.split(",").map((item) => item.trim()).filter(Boolean) })} />
      <TextField label="Начальный капитал" value={settings.initialCapital} type="number"
        onChange={(event) => updateNumber("initialCapital", event.target.value)} />
      <TextField label="Размер позиции, %" value={settings.positionSizePercent} type="number"
        onChange={(event) => updateNumber("positionSizePercent", event.target.value)} />
      <TextField label="Плечо" value={settings.leverage} type="number"
        onChange={(event) => updateNumber("leverage", event.target.value)} />
      <TextField label="Поддерживающая маржа, %" value={settings.maintenanceMarginPercent} type="number"
        onChange={(event) => updateNumber("maintenanceMarginPercent", event.target.value)} />
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Риск на сделку, %" value={settings.riskPerTradePercent} type="number"
          onChange={(event) => updateNumber("riskPerTradePercent", event.target.value)} />
        <TextField fullWidth label="Доля Kelly" value={settings.kellyFraction} type="number"
          onChange={(event) => updateNumber("kellyFraction", event.target.value)} />
      </Stack>
      <TextField fullWidth label="Порог confidence" value={settings.confidenceThreshold} type="number"
        onChange={(event) => updateNumber("confidenceThreshold", event.target.value)} />
      <Typography variant="body2" color="text.secondary">
        Stop Loss рассчитывается за структурной границей OB, цели — по ликвидности и RR выбранного JSON-шаблона.
      </Typography>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Комиссия, %" value={settings.feePercent} type="number"
          onChange={(event) => updateNumber("feePercent", event.target.value)} />
        <TextField fullWidth label="Проскальзывание, %" value={settings.slippagePercent} type="number"
          onChange={(event) => updateNumber("slippagePercent", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Funding в день, %" value={settings.fundingPercentPerDay} type="number"
          onChange={(event) => updateNumber("fundingPercentPerDay", event.target.value)} />
        <TextField fullWidth label="Trailing Stop, %" value={settings.trailingStopPercent ?? ""} type="number"
          onChange={(event) => onChange({
            ...settings,
            trailingStopPercent: event.target.value ? Number(event.target.value) : undefined,
          })} />
      </Stack>
      <Button variant="contained" size="large" disabled={!isValid || isRunning} onClick={onRun}>
        {isRunning ? `Выполняем расчёт… ${progress}%` : "Запустить бэктест"}
      </Button>
      {!isValid && <Typography variant="caption" color="error.main">
        Проверьте капитал, риск, размер позиции и параметры исполнения.
      </Typography>}
    </Stack>
  </Paper>;
}
