"use client";

import { Button, Checkbox, FormControl, FormControlLabel, InputLabel, ListItemText, MenuItem, Paper, Select, Stack, TextField, Typography } from "@mui/material";
import type { BacktestSettings, DirectionMode } from "../../lib/backtest/types";

interface BacktestSettingsFormProps {
  isRunning: boolean;
  onChange: (settings: BacktestSettings) => void;
  onRun: () => void;
  progress: number;
  settings: BacktestSettings;
  submitLabel?: string;
}

const quarterSteps = (minimum: number, maximum: number) =>
  Array.from({ length: Math.round((maximum - minimum) / 0.25) + 1 }, (_, index) => minimum + index * 0.25);

export function BacktestSettingsForm({ isRunning, onChange, onRun, progress, settings, submitLabel = "Запустить бэктест" }: BacktestSettingsFormProps) {
  const updateNumber = (key: keyof BacktestSettings, value: string) => onChange({ ...settings, [key]: Number(value) });
  const isValid = settings.initialCapital > 0 && settings.riskPerTradePercent >= 0
    && settings.elliott.takeProfitRr >= settings.elliott.minimumRr
    && settings.elliott.wave2MinRetracement < settings.elliott.wave2MaxRetracement
    && (settings.elliott.takeProfitCount === 1 || settings.elliott.secondTakeProfitRr > settings.elliott.takeProfitRr);
  const updateElliottNumber = (key: keyof BacktestSettings["elliott"], value: string) =>
    onChange({ ...settings, elliott: { ...settings.elliott, [key]: Number(value) } });
  const checkedValue = (value: unknown, display = String(value)) =>
    <Stack direction="row" spacing={1} sx={{ width: "100%", alignItems: "center" }}>
      <Checkbox checked size="small" tabIndex={-1} sx={{ p: 0, pointerEvents: "none" }} />
      <Typography component="span">{display}</Typography>
    </Stack>;
  const elliottChoice = (label: string, key: keyof BacktestSettings["elliott"], options: number[]) =>
    <FormControl fullWidth><InputLabel>{label}</InputLabel>
      <Select label={label} value={settings.elliott[key] as number}
        renderValue={(selected) => <Stack direction="row" spacing={1} sx={{ width: "100%", alignItems: "center" }}>
          <Checkbox checked size="small" tabIndex={-1} sx={{ p: 0, pointerEvents: "none" }} />
          <Typography component="span">{String(selected)}</Typography>
        </Stack>}
        onChange={(event) => updateElliottNumber(key, String(event.target.value))}>
        {options.map((option) => <MenuItem key={option} value={option}>
          <Checkbox checked={settings.elliott[key] === option} /><ListItemText primary={option} />
        </MenuItem>)}
      </Select>
    </FormControl>;
  const entryModel = settings.elliott.entryModel;
  const usesChochRetracement = entryModel === "CHOCH_RETRACE";
  const usesBreakoutBuffer = entryModel === "WAVE1_BREAK_MARKET" || entryModel === "WAVE1_BREAK_STOP";
  const usesRetestZone = entryModel === "WAVE1_BREAK_RETEST_CONFIRM";
  const usesDisplacement = entryModel === "DISPLACEMENT_RETRACE";
  const usesSweep = entryModel === "P2_LIQUIDITY_SWEEP";
  const usesVolatilityExpansion = entryModel === "VOLATILITY_EXPANSION";
  const usesVolumeExpansion = entryModel === "VOLUME_EXPANSION";
  const hasModelParameters = usesBreakoutBuffer || usesRetestZone || usesDisplacement || usesSweep
    || usesVolatilityExpansion || usesVolumeExpansion;

  return <Paper variant="outlined" sx={{ p: 3 }}>
    <Typography variant="h6">Параметры стратегии</Typography>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
      Elliott Wave на сохранённых закрытых свечах.
    </Typography>
    <Stack spacing={2}>
      <TextField
        select
        label="Направление"
        value={settings.directionMode}
        onChange={(event) => onChange({ ...settings, directionMode: event.target.value as DirectionMode })}
      >
        <MenuItem value="BOTH">Long и Short</MenuItem><MenuItem value="LONG">Только Long</MenuItem><MenuItem value="SHORT">Только Short</MenuItem>
      </TextField>
      {settings.strategy === "ELLIOTT" && <Stack spacing={1.5}>
        <Typography variant="subtitle2">Архитектура Elliott и ATR ZigZag</Typography>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          {(["macroTimeframe", "structureTimeframe", "entryTimeframe"] as const).map((key) =>
            <TextField key={key} fullWidth select label={{ macroTimeframe: "Macro TF", structureTimeframe: "Structure TF", entryTimeframe: "Entry TF" }[key]}
              value={settings.elliott[key]}
              slotProps={{ select: { renderValue: (selected) => checkedValue(selected) } }}
              onChange={(event) => onChange({ ...settings, elliott: { ...settings.elliott, [key]: event.target.value } })}>
              {timeframeOptions(key).map((tf) => <MenuItem key={tf} value={tf}>
                <Checkbox checked={settings.elliott[key] === tf} /><ListItemText primary={tf} />
              </MenuItem>)}
            </TextField>)}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("ATR период", "atrPeriod", [7, 10, 14, 20, 21, 28, 50, 100, 200])}
          {elliottChoice("Разворот ZigZag, ATR", "zigzagReversalAtr", quarterSteps(0.25, 10))}
          {elliottChoice("Мин. swing, ATR", "minSwingAtr", quarterSteps(0, 10))}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("Wave 1 мин., ATR", "wave1MinAtr", [0, 0.5, 1, 1.5, 2, 3, 5, 10, 20])}
          {elliottChoice("Wave 1 efficiency", "wave1MinEfficiency", [0, 0.25, 0.35, 0.45, 0.5, 0.6, 0.75, 1])}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("Wave 2 retracement от", "wave2MinRetracement", [0, 0.236, 0.382, 0.5, 0.618, 0.786])}
          {elliottChoice("Wave 2 retracement до", "wave2MaxRetracement", [0.236, 0.382, 0.5, 0.618, 0.786, 0.9, 0.99])}
        </Stack>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          <TextField fullWidth select label="Модель входа" value={settings.elliott.entryModel}
            sx={{ flex: 2, minWidth: { md: 360 } }}
            slotProps={{ select: { renderValue: (selected) => checkedValue(selected, {
              CHOCH_MARKET: "CHOCH market", CHOCH_RETRACE: "CHOCH retrace",
              WAVE1_BREAK_RETRACE: "P1 break + retrace",
              WAVE1_BREAK_MARKET: "Пробой P1 → market", WAVE1_BREAK_STOP: "Stop-order за P1",
              WAVE1_BREAK_RETEST_CONFIRM: "Пробой P1 + подтверждённый ретест", MICRO_WAVE3: "Micro Wave 1→2→3",
              DISPLACEMENT_RETRACE: "Displacement + retracement", P2_LIQUIDITY_SWEEP: "Ложный пробой P2",
              WAVE2_TRENDLINE_BREAK: "Пробой трендовой Wave 2", ADX_ACCELERATION: "Ускорение ADX",
              VOLATILITY_EXPANSION: "Сжатие → расширение ATR", VOLUME_EXPANSION: "Расширение объёма",
            }[String(selected)] ?? String(selected)) } }}
            onChange={(e) => onChange({ ...settings, elliott: {
              ...settings.elliott, entryModel: e.target.value as typeof settings.elliott.entryModel,
            } })}>
            <MenuItem value="CHOCH_MARKET"><Checkbox checked={settings.elliott.entryModel === "CHOCH_MARKET"} /><ListItemText primary="CHOCH market" /></MenuItem>
            <MenuItem value="CHOCH_RETRACE"><Checkbox checked={settings.elliott.entryModel === "CHOCH_RETRACE"} /><ListItemText primary="CHOCH retrace" /></MenuItem>
            <MenuItem value="WAVE1_BREAK_RETRACE"><Checkbox checked={settings.elliott.entryModel === "WAVE1_BREAK_RETRACE"} /><ListItemText primary="P1 break + retrace" /></MenuItem>
            <MenuItem value="WAVE1_BREAK_MARKET"><Checkbox checked={settings.elliott.entryModel === "WAVE1_BREAK_MARKET"} /><ListItemText primary="Пробой Wave 1 High/Low → market" /></MenuItem>
            <MenuItem value="WAVE1_BREAK_STOP"><Checkbox checked={settings.elliott.entryModel === "WAVE1_BREAK_STOP"} /><ListItemText primary="Stop-order за Wave 1 High/Low" /></MenuItem>
            <MenuItem value="WAVE1_BREAK_RETEST_CONFIRM"><Checkbox checked={settings.elliott.entryModel === "WAVE1_BREAK_RETEST_CONFIRM"} /><ListItemText primary="Пробой P1 + подтверждённый ретест" /></MenuItem>
            <MenuItem value="MICRO_WAVE3"><Checkbox checked={settings.elliott.entryModel === "MICRO_WAVE3"} /><ListItemText primary="Micro Wave 1 → Wave 2 → Wave 3" /></MenuItem>
            <MenuItem value="DISPLACEMENT_RETRACE"><Checkbox checked={settings.elliott.entryModel === "DISPLACEMENT_RETRACE"} /><ListItemText primary="Displacement + retracement" /></MenuItem>
            <MenuItem value="P2_LIQUIDITY_SWEEP"><Checkbox checked={settings.elliott.entryModel === "P2_LIQUIDITY_SWEEP"} /><ListItemText primary="Ложный пробой экстремума Wave 2" /></MenuItem>
            <MenuItem value="WAVE2_TRENDLINE_BREAK"><Checkbox checked={settings.elliott.entryModel === "WAVE2_TRENDLINE_BREAK"} /><ListItemText primary="Пробой локальной трендовой Wave 2" /></MenuItem>
            <MenuItem value="ADX_ACCELERATION"><Checkbox checked={settings.elliott.entryModel === "ADX_ACCELERATION"} /><ListItemText primary="ADX acceleration" /></MenuItem>
            <MenuItem value="VOLATILITY_EXPANSION"><Checkbox checked={settings.elliott.entryModel === "VOLATILITY_EXPANSION"} /><ListItemText primary="Volatility expansion" /></MenuItem>
            <MenuItem value="VOLUME_EXPANSION"><Checkbox checked={settings.elliott.entryModel === "VOLUME_EXPANSION"} /><ListItemText primary="Volume expansion" /></MenuItem>
          </TextField>
          {usesChochRetracement && elliottChoice("Доля импульса от CHOCH (0 = ретест уровня)", "entryRetracement", [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1])}
          {elliottChoice("Ждать вход, свечей", "entryExpiryBars", [1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100])}
        </Stack>
        {hasModelParameters && <Paper variant="outlined" sx={{ p: 2 }}><Stack spacing={1.5}>
          <Typography variant="subtitle2">Параметры выбранной модели</Typography>
          {(usesBreakoutBuffer || usesRetestZone || usesSweep) && <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {usesBreakoutBuffer && <TextField fullWidth label="Буфер пробоя P1, ATR" type="number" value={settings.elliott.breakoutBufferAtr}
              slotProps={{ htmlInput: { min: 0, max: 5, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("breakoutBufferAtr", event.target.value)} />}
            {usesRetestZone && <TextField fullWidth label="Зона ретеста P1, ATR" type="number" value={settings.elliott.retestZoneAtr}
              slotProps={{ htmlInput: { min: 0, max: 5, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("retestZoneAtr", event.target.value)} />}
            {usesSweep && <TextField fullWidth label="Мин. тень sweep P2" type="number" value={settings.elliott.sweepMinWickRatio}
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("sweepMinWickRatio", event.target.value)} />}
          </Stack>}
          {usesDisplacement && <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            <TextField fullWidth label="Displacement, ATR" type="number" value={settings.elliott.displacementMinAtr}
              slotProps={{ htmlInput: { min: 0.1, max: 20, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("displacementMinAtr", event.target.value)} />
            <TextField fullWidth label="Displacement body ratio" type="number"
              value={settings.elliott.displacementMinBodyRatio} slotProps={{ htmlInput: { min: 0, max: 1, step: 0.05 } }}
              onChange={(event) => updateElliottNumber("displacementMinBodyRatio", event.target.value)} />
            <TextField fullWidth label="Откат displacement" type="number" value={settings.elliott.displacementRetracement}
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("displacementRetracement", event.target.value)} />
          </Stack>}
          {(usesVolatilityExpansion || usesVolumeExpansion) && <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            {usesVolatilityExpansion && <TextField fullWidth label="Расширение ATR, ×" type="number" value={settings.elliott.volatilityExpansionRatio}
              slotProps={{ htmlInput: { min: 1, max: 20, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("volatilityExpansionRatio", event.target.value)} />}
            {usesVolumeExpansion && <TextField fullWidth label="Расширение объёма, × SMA20" type="number" value={settings.elliott.volumeExpansionRatio}
              slotProps={{ htmlInput: { min: 1, max: 100, step: 0.1 } }}
              onChange={(event) => updateElliottNumber("volumeExpansionRatio", event.target.value)} />}
            {usesVolumeExpansion && <TextField fullWidth label="Volume body ratio" type="number" value={settings.elliott.volumeExpansionMinBodyRatio}
              slotProps={{ htmlInput: { min: 0, max: 1, step: 0.05 } }}
              onChange={(event) => updateElliottNumber("volumeExpansionMinBodyRatio", event.target.value)} />}
          </Stack>}
        </Stack></Paper>}
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("CHOCH displacement, ATR", "chochMinAtr", [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
          {elliottChoice("Мин. тело свечи", "chochMinBodyRatio", [0, 0.25, 0.35, 0.5, 0.6, 0.75, 1])}
        </Stack>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
          {elliottChoice("Период ADX", "adxPeriod", [7, 10, 14, 20, 21, 28, 50, 100])}
          <TextField fullWidth label="Минимальный ADX" type="number" value={settings.elliott.adxMin}
            helperText="0 отключает фильтр силы тренда"
            slotProps={{ htmlInput: { min: 0, max: 100, step: 0.5 } }}
            onChange={(e) => updateElliottNumber("adxMin", e.target.value)} />
          <FormControlLabel sx={{ minWidth: 250 }} control={<Checkbox checked={settings.elliott.requireDiConfirmation}
            onChange={(e) => onChange({ ...settings, elliott: { ...settings.elliott, requireDiConfirmation: e.target.checked } })} />}
            label="Требовать подтверждение +DI/-DI" />
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("Буфер стопа, ATR", "stopBufferAtr", [0, 0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
          <TextField fullWidth label="Минимальный RR" type="number" value={settings.elliott.minimumRr} onChange={(e) => updateElliottNumber("minimumRr", e.target.value)} />
        </Stack>
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1.5}>
            <Typography variant="subtitle2">Тейки и управление позицией</Typography>
            <Typography variant="body2" color="text.secondary">
              RR задаёт расстояние от входа до тейка в долях расстояния до структурного стопа.
            </Typography>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
              <TextField fullWidth select label="Количество тейков" value={settings.elliott.takeProfitCount}
                onChange={(e) => onChange({ ...settings, elliott: { ...settings.elliott, takeProfitCount: Number(e.target.value) as 1 | 2 } })}>
                <MenuItem value={1}>1 тейк — закрыть всю позицию</MenuItem>
                <MenuItem value={2}>2 тейка — управление на TP1</MenuItem>
              </TextField>
              <TextField fullWidth label="TP1, RR" type="number" value={settings.elliott.takeProfitRr}
                slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }} onChange={(e) => updateElliottNumber("takeProfitRr", e.target.value)} />
              {settings.elliott.takeProfitCount === 2 && <TextField fullWidth label="TP2, RR" type="number" value={settings.elliott.secondTakeProfitRr}
                slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }} onChange={(e) => updateElliottNumber("secondTakeProfitRr", e.target.value)} />}
            </Stack>
            {settings.elliott.takeProfitCount === 2 && <TextField fullWidth select label="Что делать при достижении TP1"
              value={settings.elliott.firstTakeAction} onChange={(e) => onChange({ ...settings, elliott: {
                ...settings.elliott,
                firstTakeAction: e.target.value as BacktestSettings["elliott"]["firstTakeAction"],
              } })}>
              <MenuItem value="PARTIAL_CLOSE">Закрыть 50%, остаток держать до TP2</MenuItem>
              <MenuItem value="MOVE_TO_BREAK_EVEN">Не закрывать, перенести стоп всей позиции в безубыток</MenuItem>
            </TextField>}
            {settings.elliott.takeProfitCount === 2 && <Typography variant="caption" color="text.secondary">
              Безубыток учитывает комиссии входа и выхода, проскальзывание и биржевой шаг цены.
            </Typography>}
          </Stack>
        </Paper>
      </Stack>}
      <TextField label="Начальный капитал" value={settings.initialCapital} type="number"
        onChange={(event) => updateNumber("initialCapital", event.target.value)} />
      {settings.strategy === "ELLIOTT" && <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="subtitle2">Капитал, риск и маржа</Typography>
          <TextField fullWidth select label="Режим позиции" value={settings.elliott.useMargin ? "MARGIN" : "CASH"}
            onChange={(event) => onChange({ ...settings, elliott: {
              ...settings.elliott, useMargin: event.target.value === "MARGIN",
            } })}>
            <MenuItem value="CASH">Без маржи — только доступный капитал</MenuItem>
            <MenuItem value="MARGIN">Использовать маржу и плечо</MenuItem>
          </TextField>
          <TextField fullWidth select label="Реинвестирование прибыли" value={settings.elliott.reinvestProfits ? "ON" : "OFF"}
            onChange={(event) => onChange({ ...settings, elliott: {
              ...settings.elliott, reinvestProfits: event.target.value === "ON",
            } })}>
            <MenuItem value="ON">Включено — увеличивать следующие позиции</MenuItem>
            <MenuItem value="OFF">Выключено — не превышать начальный капитал</MenuItem>
          </TextField>
          {settings.elliott.useMargin && <Stack direction={{ xs: "column", md: "row" }} spacing={1.5}>
            <TextField fullWidth label="Плечо" value={settings.leverage} type="number"
              slotProps={{ htmlInput: { min: 1, max: 100, step: 1 } }}
              onChange={(event) => updateNumber("leverage", event.target.value)} />
          </Stack>}
          <FormControlLabel control={<Checkbox checked={settings.riskPerTradePercent > 0}
            onChange={(event) => onChange({ ...settings, riskPerTradePercent: event.target.checked ? 1 : 0 })} />}
            label="Ограничивать риск на сделку" />
          {settings.riskPerTradePercent > 0 && <TextField fullWidth label="Собственный риск на сделку, %" value={settings.riskPerTradePercent} type="number"
            helperText="Максимальный убыток до структурного стопа. Верхнего ограничения нет; фактический объём ограничен капиталом и плечом."
            slotProps={{ htmlInput: { min: 0.01, step: 0.1 } }}
            onChange={(event) => updateNumber("riskPerTradePercent", event.target.value)} />
          }
          {settings.riskPerTradePercent === 0 && <Typography variant="body2" color="warning.main">
            Риск-лимит отключён: позиция использует весь доступный номинал по выбранному плечу.
          </Typography>}
          <Typography variant="caption" color="text.secondary">
            Размер позиции ограничен выбранным риском. Без маржи номинал не превышает капитал;
            с маржой — капитал × плечо. Комиссии считаются со всего номинала.
          </Typography>
        </Stack>
      </Paper>}
      <Typography variant="body2" color="text.secondary">
        Stop Loss рассчитывается за структурной границей Elliott, тейки — по заданному Risk/Reward.
      </Typography>
      <><Stack direction="row" spacing={1.5}>
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
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Шаг цены" value={settings.tickSize} type="number"
          onChange={(event) => updateNumber("tickSize", event.target.value)} />
      </Stack>
      <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Ликвидация, %" value={settings.liquidationFeePercent} type="number"
          onChange={(event) => updateNumber("liquidationFeePercent", event.target.value)} />
      </Stack></>
      <Button variant="contained" size="large" disabled={!isValid || isRunning} onClick={onRun}>
        {isRunning ? (progress > 0 ? `Выполняем расчёт… ${progress}%` : "Сохраняем…") : submitLabel}
      </Button>
      {!isValid && <Typography variant="caption" color="error.main">
        Проверьте капитал, риск и параметры Elliott/Risk-Reward.
      </Typography>}
    </Stack>
  </Paper>;
}

function timeframeOptions(key: "macroTimeframe" | "structureTimeframe" | "entryTimeframe") {
  if (key === "macroTimeframe") return ["H1", "H4", "D1"];
  if (key === "structureTimeframe") return ["M15", "M30", "H1", "H4"];
  return ["M1", "M5", "M15", "M30"];
}
