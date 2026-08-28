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
    && (settings.strategy === "ELLIOTT"
      || (settings.positionSizePercent > 0 && settings.positionSizePercent <= 100))
    && settings.riskPerTradePercent > 0
    && (settings.strategy !== "ELLIOTT" || (settings.elliott.takeProfitRr > 0
      && settings.elliott.wave2MinRetracement < settings.elliott.wave2MaxRetracement
      && (settings.elliott.takeProfitCount === 1 || settings.elliott.secondTakeProfitRr > settings.elliott.takeProfitRr)))
    && (settings.strategy !== "SMC" || (settings.smcMinTargetRr > 0 && settings.smcMaxTargetRr > settings.smcMinTargetRr
      && (settings.smcTargetMode === "TEMPLATE" || settings.smcTargetRr > 0)))
    && (settings.strategy !== "SMC" || settings.templateIds.length > 0);
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
              slotProps={{ select: { renderValue: (selected) => checkedValue(selected) } }}
              onChange={(event) => onChange({ ...settings, elliott: { ...settings.elliott, [key]: event.target.value } })}>
              {timeframeOptions(key).map((tf) => <MenuItem key={tf} value={tf}>
                <Checkbox checked={settings.elliott[key] === tf} /><ListItemText primary={tf} />
              </MenuItem>)}
            </TextField>)}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("ATR период", "atrPeriod", [7, 10, 14, 20, 21, 28, 50, 100, 200])}
          {elliottChoice("Разворот ZigZag, ATR", "zigzagReversalAtr", [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
          {elliottChoice("Мин. swing, ATR", "minSwingAtr", [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("Wave 1 мин., ATR", "wave1MinAtr", [0, 0.5, 1, 1.5, 2, 3, 5, 10, 20])}
          {elliottChoice("Wave 1 efficiency", "wave1MinEfficiency", [0, 0.25, 0.35, 0.45, 0.5, 0.6, 0.75, 1])}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("Wave 2 retracement от", "wave2MinRetracement", [0, 0.236, 0.382, 0.5, 0.618, 0.786])}
          {elliottChoice("Wave 2 retracement до", "wave2MaxRetracement", [0.236, 0.382, 0.5, 0.618, 0.786, 0.9, 0.99])}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          <TextField fullWidth select label="Модель входа" value={settings.elliott.entryModel}
            slotProps={{ select: { renderValue: (selected) => checkedValue(selected, {
              CHOCH_MARKET: "CHOCH market", CHOCH_RETRACE: "CHOCH retrace",
              WAVE1_BREAK_RETRACE: "P1 break + retrace",
            }[String(selected)] ?? String(selected)) } }}
            onChange={(e) => onChange({ ...settings, elliott: {
              ...settings.elliott, entryModel: e.target.value as typeof settings.elliott.entryModel,
            } })}>
            <MenuItem value="CHOCH_MARKET"><Checkbox checked={settings.elliott.entryModel === "CHOCH_MARKET"} /><ListItemText primary="CHOCH market" /></MenuItem>
            <MenuItem value="CHOCH_RETRACE"><Checkbox checked={settings.elliott.entryModel === "CHOCH_RETRACE"} /><ListItemText primary="CHOCH retrace" /></MenuItem>
            <MenuItem value="WAVE1_BREAK_RETRACE"><Checkbox checked={settings.elliott.entryModel === "WAVE1_BREAK_RETRACE"} /><ListItemText primary="P1 break + retrace" /></MenuItem>
          </TextField>
          {elliottChoice("Retracement входа", "entryRetracement", [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1])}
          {elliottChoice("Ждать вход, свечей", "entryExpiryBars", [1, 2, 3, 4, 5, 8, 10, 15, 20, 50, 100])}
        </Stack>
        <Stack direction="row" spacing={1.5}>
          {elliottChoice("CHOCH displacement, ATR", "chochMinAtr", [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 5, 10])}
          {elliottChoice("Мин. тело свечи", "chochMinBodyRatio", [0, 0.25, 0.35, 0.5, 0.6, 0.75, 1])}
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
              onChange={(event) => updateNumber("leverage", event.target.value)} />
          </Stack>}
          <Typography variant="caption" color="text.secondary">
            Весь капитал выделен этому активу. Без маржи номинал равен капиталу;
            с маржой номинал равен капиталу × плечо. Комиссии считаются со всего номинала.
          </Typography>
        </Stack>
      </Paper>}
      {settings.strategy !== "ELLIOTT" && <>
        <TextField label="Размер позиции, %" value={settings.positionSizePercent} type="number"
          onChange={(event) => updateNumber("positionSizePercent", event.target.value)} />
        <TextField label="Плечо" value={settings.leverage} type="number"
          onChange={(event) => updateNumber("leverage", event.target.value)} />
      </>}
      {settings.strategy !== "ELLIOTT" && <Stack direction="row" spacing={1.5}>
        <TextField fullWidth label="Риск на сделку, %" value={settings.riskPerTradePercent} type="number"
          onChange={(event) => updateNumber("riskPerTradePercent", event.target.value)} />
        <TextField fullWidth label="Доля Kelly" value={settings.kellyFraction} type="number"
          onChange={(event) => updateNumber("kellyFraction", event.target.value)} />
      </Stack>}
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
