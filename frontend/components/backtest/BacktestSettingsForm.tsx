"use client";

import { Button, Checkbox, FormControl, InputLabel, ListItemText, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import type { BacktestSettings, DirectionMode, StrategyType } from "../../lib/backtest/types";

interface BacktestSettingsFormProps {
  isRunning: boolean;
  onChange: (settings: BacktestSettings) => void;
  onRun: () => void;
  progress: number;
  settings: BacktestSettings;
  templates: Array<{ id: string; name: string }>;
}

export function BacktestSettingsForm({ isRunning, onChange, onRun, progress, settings, templates }: BacktestSettingsFormProps) {
  const updateNumber = (key: keyof BacktestSettings, value: string) => onChange({ ...settings, [key]: Number(value) });
  const isValid = settings.initialCapital > 0
    && settings.positionSizePercent > 0
    && settings.positionSizePercent <= 100
    && settings.riskPerTradePercent > 0
    && (settings.strategy !== "SMC" || (settings.smcMinTargetRr > 0 && settings.smcMaxTargetRr > settings.smcMinTargetRr
      && (settings.smcTargetMode === "TEMPLATE" || settings.smcTargetRr > 0)))
    && (settings.strategy !== "SMC" || settings.templateIds.length > 0);
  const updateElliottNumber = (key: keyof BacktestSettings["elliott"], value: string) =>
    onChange({ ...settings, elliott: { ...settings.elliott, [key]: Number(value) } });

  return <Paper variant="outlined" sx={{ p: 3 }}>
    <Typography variant="h6">Параметры стратегии</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
      SMC или Elliott replay на сохранённых закрытых свечах без заглядывания вперёд.
    </Typography>
    <Stack spacing={2}>
      <TextField select label="Стратегия" value={settings.strategy}
        onChange={(event) => onChange({ ...settings, strategy: event.target.value as StrategyType })}>
        <MenuItem value="ELLIOTT">Elliott Wave</MenuItem><MenuItem value="SMC">Smart Money Concept</MenuItem>
      </TextField>
      <TextField
        select
        label="Направление"
        value={settings.directionMode}
        onChange={(event) => onChange({ ...settings, directionMode: event.target.value as DirectionMode })}
      >
        <MenuItem value="BOTH">Long и Short</MenuItem><MenuItem value="LONG">Только Long</MenuItem><MenuItem value="SHORT">Только Short</MenuItem>
      </TextField>
      {settings.strategy === "SMC" && <FormControl fullWidth>
        <InputLabel id="backtest-templates-label">Шаблоны для теста</InputLabel>
        <Select
          labelId="backtest-templates-label"
          multiple
          label="Шаблоны для теста"
          value={settings.templateIds}
          onChange={(event) => onChange({
            ...settings,
            templateIds: typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value,
          })}
          renderValue={(selected) => `Выбрано: ${selected.length}`}
        >
          {templates.map((template) => <MenuItem key={template.id} value={template.id}>
            <Checkbox checked={settings.templateIds.includes(template.id)} />
            <ListItemText primary={template.name} secondary={template.id} />
          </MenuItem>)}
        </Select>
      </FormControl>}
      {settings.strategy === "SMC" && <Typography variant="body2" color="text.secondary">
        В расчёте участвуют только отмеченные шаблоны и их собственные роли таймфреймов.
      </Typography>}
      {settings.strategy === "ELLIOTT" && <Stack spacing={1.5}>
        <Typography variant="subtitle2">Архитектура Elliott и ATR ZigZag</Typography>
        <Stack direction="row" spacing={1.5}>
          {(["macroTimeframe", "structureTimeframe", "entryTimeframe"] as const).map((key) =>
            <TextField key={key} fullWidth select label={{ macroTimeframe: "Macro TF", structureTimeframe: "Structure TF", entryTimeframe: "Entry TF" }[key]}
              value={settings.elliott[key]}
              onChange={(event) => onChange({ ...settings, elliott: { ...settings.elliott, [key]: event.target.value } })}>
              {timeframeOptions(key).map((tf) => <MenuItem key={tf} value={tf}>{tf}</MenuItem>)}
            </TextField>)}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth label="ATR период" type="number" value={settings.elliott.atrPeriod} onChange={(e) => updateElliottNumber("atrPeriod", e.target.value)} />
          <TextField fullWidth label="Разворот ZigZag, ATR" type="number" value={settings.elliott.zigzagReversalAtr} onChange={(e) => updateElliottNumber("zigzagReversalAtr", e.target.value)} />
          <TextField fullWidth label="Мин. swing, ATR" type="number" value={settings.elliott.minSwingAtr} onChange={(e) => updateElliottNumber("minSwingAtr", e.target.value)} />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth label="Wave 1 мин., ATR" type="number" value={settings.elliott.wave1MinAtr} onChange={(e) => updateElliottNumber("wave1MinAtr", e.target.value)} />
          <TextField fullWidth label="Wave 1 efficiency" type="number" value={settings.elliott.wave1MinEfficiency} onChange={(e) => updateElliottNumber("wave1MinEfficiency", e.target.value)} />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth label="Wave 2 retracement от" type="number" value={settings.elliott.wave2MinRetracement} onChange={(e) => updateElliottNumber("wave2MinRetracement", e.target.value)} />
          <TextField fullWidth label="Wave 2 retracement до" type="number" value={settings.elliott.wave2MaxRetracement} onChange={(e) => updateElliottNumber("wave2MaxRetracement", e.target.value)} />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth select label="Модель входа" value={settings.elliott.entryModel}
            onChange={(e) => onChange({ ...settings, elliott: {
              ...settings.elliott, entryModel: e.target.value as typeof settings.elliott.entryModel,
            } })}>
            <MenuItem value="CHOCH_MARKET">CHOCH market</MenuItem><MenuItem value="CHOCH_RETRACE">CHOCH retrace</MenuItem><MenuItem value="WAVE1_BREAK_RETRACE">P1 break + retrace</MenuItem>
          </TextField>
          <TextField fullWidth label="Retracement входа" type="number" value={settings.elliott.entryRetracement} onChange={(e) => updateElliottNumber("entryRetracement", e.target.value)} />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth label="CHOCH displacement, ATR" type="number" value={settings.elliott.chochMinAtr} onChange={(e) => updateElliottNumber("chochMinAtr", e.target.value)} />
          <TextField fullWidth label="Мин. тело свечи" type="number" value={settings.elliott.chochMinBodyRatio} onChange={(e) => updateElliottNumber("chochMinBodyRatio", e.target.value)} />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth label="Буфер стопа, ATR" type="number" value={settings.elliott.stopBufferAtr} onChange={(e) => updateElliottNumber("stopBufferAtr", e.target.value)} />
          <TextField fullWidth label="Минимальный RR" type="number" value={settings.elliott.minimumRr} onChange={(e) => updateElliottNumber("minimumRr", e.target.value)} />
        </Stack>
      </Stack>}
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
      {settings.strategy === "SMC" && <TextField fullWidth label="Порог confidence" value={settings.confidenceThreshold} type="number"
        onChange={(event) => updateNumber("confidenceThreshold", event.target.value)} />}
      {settings.strategy === "SMC" && <TextField fullWidth select label="Управление Risk/Reward" value={settings.smcTargetMode}
        onChange={(event) => onChange({ ...settings, smcTargetMode: event.target.value as BacktestSettings["smcTargetMode"] })}>
        <MenuItem value="TEMPLATE">По шаблону, в заданном диапазоне</MenuItem>
        <MenuItem value="FIXED">Фиксированная цель</MenuItem>
      </TextField>}
      {settings.strategy === "SMC" && <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Risk/Reward: минимум" value={settings.smcMinTargetRr} type="number"
          slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }} onChange={(event) => updateNumber("smcMinTargetRr", event.target.value)} />
        <TextField fullWidth label="Risk/Reward: максимум" value={settings.smcMaxTargetRr} type="number"
          slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }} onChange={(event) => updateNumber("smcMaxTargetRr", event.target.value)} />
      </Stack>}
      {settings.strategy === "SMC" && settings.smcTargetMode === "FIXED" && <TextField fullWidth label="Фиксированный Risk/Reward" value={settings.smcTargetRr} type="number"
        slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }} onChange={(event) => updateNumber("smcTargetRr", event.target.value)} />}
      <Typography variant="body2" color="text.secondary">
        Stop Loss рассчитывается за структурной границей OB, тейк выставляется на указанном расстоянии Risk/Reward.
      </Typography>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Maker, %" value={settings.makerFeePercent} type="number"
          onChange={(event) => updateNumber("makerFeePercent", event.target.value)} />
        <TextField fullWidth label="Taker, %" value={settings.takerFeePercent} type="number"
          onChange={(event) => updateNumber("takerFeePercent", event.target.value)} />
        <TextField fullWidth label="Проскальзывание, %" value={settings.slippagePercent} type="number"
          onChange={(event) => updateNumber("slippagePercent", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Funding в день, %" value={settings.fundingPercentPerDay} type="number"
          onChange={(event) => updateNumber("fundingPercentPerDay", event.target.value)} />
        <TextField fullWidth label="Funding интервал, ч" value={settings.fundingIntervalHours} type="number"
          onChange={(event) => updateNumber("fundingIntervalHours", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Задержка, мс" value={settings.executionLatencyMs} type="number"
          onChange={(event) => updateNumber("executionLatencyMs", event.target.value)} />
        <TextField fullWidth label="Доля объёма, %" value={settings.volumeParticipationPercent} type="number"
          onChange={(event) => updateNumber("volumeParticipationPercent", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Шаг цены" value={settings.tickSize} type="number"
          onChange={(event) => updateNumber("tickSize", event.target.value)} />
        <TextField fullWidth label="Шаг количества" value={settings.lotSize} type="number"
          onChange={(event) => updateNumber("lotSize", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Мин. ордер" value={settings.minimumOrderSize} type="number"
          onChange={(event) => updateNumber("minimumOrderSize", event.target.value)} />
        <TextField fullWidth label="Ликвидация, %" value={settings.liquidationFeePercent} type="number"
          onChange={(event) => updateNumber("liquidationFeePercent", event.target.value)} />
      </Stack>
      <Button variant="contained" size="large" disabled={!isValid || isRunning} onClick={onRun}>
        {isRunning ? `Выполняем расчёт… ${progress}%` : "Запустить бэктест"}
      </Button>
      {!isValid && <Typography variant="caption" color="error.main">
        Проверьте капитал, риск, Risk/Reward, размер позиции, параметры исполнения и выберите хотя бы один шаблон.
      </Typography>}
    </Stack>
  </Paper>;
}

function timeframeOptions(key: "macroTimeframe" | "structureTimeframe" | "entryTimeframe") {
  if (key === "macroTimeframe") return ["H1", "H4", "D1"];
  if (key === "structureTimeframe") return ["M15", "M30", "H1", "H4"];
  return ["M1", "M5", "M15", "M30"];
}
