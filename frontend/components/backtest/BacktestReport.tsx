"use client";

import { Alert, Box, Chip, Grid, LinearProgress, ListSubheader, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import type { BacktestResult, BacktestTrade } from "../../lib/backtest/types";
import { EquityChart } from "./EquityChart";
import { BacktestPriceChart } from "./BacktestPriceChart";

interface MetricProps { label: string; value: string; tone?: "success" | "error" }

const diagnosticLabels: Record<string,{ title: string; hint: string }> = {
  NO_CONTEXT_STRUCTURE: { title: "Нет направления на старших ТФ", hint: "На context-ТФ шаблона не найден подходящий BOS, CHoCH или MSS." },
  NO_ZONE_TOUCH: { title: "Цена не коснулась Order Block", hint: "Контекст найден, но цена не вернулась в активный OB заданного таймфрейма." },
  NO_FVG_TOUCH: { title: "Цена не коснулась FVG", hint: "Не было возврата цены в незаполненный imbalance/FVG." },
  NO_OB_FVG_OVERLAP: { title: "OB и FVG не пересекаются", hint: "Обе зоны существуют, но не образуют требуемую общую область входа." },
  NO_OB_RETEST: { title: "Нет ретеста Order Block", hint: "Order Block ещё не был повторно протестирован ценой." },
  NO_DIRECTION_SOURCE: { title: "Не определена сторона сделки", hint: "Источник направления, указанный в шаблоне, отсутствует." },
  DIRECTION_NOT_ALLOWED: { title: "Направление запрещено шаблоном", hint: "Шаблон разрешает только другую сторону сделки." },
  STOP_TOO_TIGHT: { title: "Стоп слишком близкий", hint: "Структурный стоп меньше minimum_stop_percent шаблона." },
  STOP_TOO_WIDE: { title: "Стоп слишком широкий", hint: "Структурный стоп больше maximum_stop_percent шаблона." },
  REJECTED_STOP_DISTANCE: { title: "Стоп вне диапазона при исполнении", hint: "После учёта фактической цены входа стоп вышел за диапазон шаблона." },
  NO_PRIMARY_CONTEXT: { title: "Нет структуры главного ТФ", hint: "На primary_context_timeframe не найдено событие направления." },
  NO_PRIMARY_ALIGNMENT: { title: "Главный ТФ не подтверждён", hint: "Тренд главного context-ТФ не совпадает с направлением сделки." },
  HTF_CONTEXT_CONFLICT: { title: "Конфликт старших ТФ", hint: "Один из дополнительных context-ТФ направлен против главного." },
  EVENT_SEQUENCE_MISSING: { title: "Нет события последовательности", hint: "Не найден sweep, confirmation или touch, обязательный шаблону." },
  EVENT_SEQUENCE_WRONG_ORDER: { title: "Нарушен порядок событий", hint: "События произошли не в порядке event_sequence шаблона." },
  ZONE_CREATED_AFTER_CONFIRMATION: { title: "Зона появилась слишком поздно", hint: "Шаблон требует существования зоны до подтверждения." },
  REJECTED_ZONE_REUSE: { title: "Повторный вход в зону", hint: "Шаблон разрешает только одну сделку на Order Block." },
  REJECTED_COOLDOWN: { title: "Cooldown после стопа", hint: "После стопа ещё не прошло заданное шаблоном число свечей." },
  NO_TRIGGER_CONFIRMATION: { title: "Нет подтверждения на младшем ТФ", hint: "В заданном окне не появился требуемый BOS, CHoCH или MSS." },
  NO_TRIGGER_BOS: { title: "Нет локального BOS", hint: "Продолжение структуры на trigger-ТФ не подтверждено." },
  NO_TRIGGER_CHOCH_MSS: { title: "Нет локального CHoCH/MSS", hint: "Разворот структуры на trigger-ТФ не подтвержден." },
  NO_LIQUIDITY_SWEEP: { title: "Не снята ликвидность", hint: "Не найден SFP/sweep нужного пула ликвидности." },
  NO_LIQUIDITY_SWEEP_BEFORE_OB: { title: "Нет sweep до Order Block", hint: "Перед исходной свечой OB не снят нужный пул ликвидности." },
  OB_OUTSIDE_OTE_ZONE: { title: "Order Block вне OTE", hint: "Середина OB находится вне зоны коррекции 61.8–78.6% последней структурной ноги." },
  NO_OTE_STRUCTURAL_LEG: { title: "Нет структурной ноги для OTE", hint: "Недостаточно подтверждённых swing high/low для построения OTE." },
  OB_DID_NOT_CAUSE_BOS: { title: "OB не связан с BOS", hint: "Order Block не имеет строгой связи с displacement и конкретным пробоем структуры." },
  WRONG_PREMIUM_DISCOUNT: { title: "Цена не в нужной половине диапазона", hint: "Long ожидается в discount, Short — в premium." },
  NO_HTF_ALIGNMENT: { title: "Старшие ТФ не согласованы", hint: "Недостаточно старших таймфреймов направлены в сторону сделки." },
  NO_TARGET_LIQUIDITY: { title: "Нет ликвидности для цели", hint: "За точкой входа не найден подходящий целевой пул ликвидности." },
  NO_M15_TREND: { title: "Не определён тренд M15", hint: "Для входа требуется подтверждённое направление структуры на M15." },
  TARGET_RR_TOO_LOW: { title: "Ликвидность слишком близко", hint: "Ближайший целевой пул не обеспечивает минимально допустимый RR." },
  REJECTED_TARGET_RR: { title: "RR цели изменился при исполнении", hint: "После фактической цены входа и корректировки стопа цель перестала удовлетворять диапазону RR." },
  DUPLICATE: { title: "Сценарий уже существует", hint: "Та же комбинация объектов уже была зарегистрирована ранее." },
};

function Metric({ label, tone, value }: MetricProps) {
  return <Paper variant="outlined" sx={{ p: 2.5 }}>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography variant="h5" color={tone ? `${tone}.main` : "text.primary"} sx={{ mt: 1 }}>{value}</Typography>
  </Paper>;
}

const monthKey = (timestamp: number) => {
  const date = new Date(timestamp);
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth()+1).padStart(2,"0")}`;
};
const quarterKey = (timestamp: number) => {
  const date = new Date(timestamp);
  return `${date.getUTCFullYear()}-Q${Math.floor(date.getUTCMonth()/3)+1}`;
};
const monthLabel = (key: string) => new Date(`${key}-01T00:00:00Z`).toLocaleDateString("ru-RU", {
  month: "long", year: "numeric", timeZone: "UTC",
});
const marginValue = (trade: BacktestTrade, leverage?: number) => {
  const notional = trade.entryPrice*trade.quantity;
  if (leverage) return notional/leverage;
  return Math.abs(trade.pnlPercent) > 1e-12 ? Math.abs(trade.pnl/(trade.pnlPercent/100)) : notional;
};
const summarize = (trades: BacktestTrade[], initialCapital: number, leverage?: number) => ({
  trades: trades.length,
  wins: trades.filter((trade) => trade.pnl > 0).length,
  pnl: trades.reduce((sum,trade) => sum+trade.pnl,0),
  notional: trades.reduce((sum,trade) => sum+trade.entryPrice*trade.quantity,0),
  margin: trades.reduce((sum,trade) => sum+marginValue(trade,leverage),0),
  returnPercent: trades.reduce((sum,trade) => sum+trade.pnl,0)/initialCapital*100,
});

export function BacktestReport({ result }: { result: BacktestResult }) {
  const profitTone = result.netProfit >= 0 ? "success" : "error";
  const [tradePage, setTradePage] = useState(0);
  const [tradesPerPage, setTradesPerPage] = useState(10);
  const [tradePeriod, setTradePeriod] = useState("ALL");
  const months = useMemo(() => [...new Set(result.trades.map((trade) => monthKey(trade.exitTime)))].sort().reverse(), [result.trades]);
  const quarters = useMemo(() => [...new Set(result.trades.map((trade) => quarterKey(trade.exitTime)))].sort().reverse(), [result.trades]);
  const filteredTrades = useMemo(() => result.trades.filter((trade) => tradePeriod === "ALL"
    || (tradePeriod.startsWith("M:") ? monthKey(trade.exitTime) === tradePeriod.slice(2)
      : quarterKey(trade.exitTime) === tradePeriod.slice(2))), [result.trades, tradePeriod]);
  const visibleTrades = filteredTrades.slice(tradePage*tradesPerPage,tradePage*tradesPerPage+tradesPerPage);
  const leverage = result.strategyConfig?.leverage;
  const scenariosById = useMemo(() => new Map(result.scenarios.map((scenario) => [scenario.id,scenario])), [result.scenarios]);
  const periodicMetrics = useMemo(() => ({
    months: months.map((key) => ({ key, label: monthLabel(key), ...summarize(
      result.trades.filter((trade) => monthKey(trade.exitTime) === key), result.initialCapital, leverage,
    ) })),
    quarters: quarters.map((key) => ({ key, label: key.replace("-Q", " · Q"), ...summarize(
      result.trades.filter((trade) => quarterKey(trade.exitTime) === key), result.initialCapital, leverage,
    ) })),
  }), [leverage, months, quarters, result.initialCapital, result.trades]);
  const period = result.dataset?.testFrom && result.dataset?.testTo
    ? `${new Date(result.dataset.testFrom).toLocaleDateString("ru-RU")} — ${new Date(result.dataset.testTo).toLocaleDateString("ru-RU")}`
    : "—";
  return <>
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Итоговый капитал" value={result.finalCapital.toFixed(2)} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Доходность" value={`${result.totalReturnPercent.toFixed(2)}%`} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Макс. просадка" value={`${result.maxDrawdownPercent.toFixed(2)}%`} tone="error" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Win rate" value={`${result.winRate.toFixed(1)}%`} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Сделок" value={String(result.totalTrades)} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Profit factor" value={result.profitFactor?.toFixed(2) ?? "—"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Средняя сделка" value={result.averageTrade.toFixed(2)} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Чистый PnL" value={result.netProfit.toFixed(2)} tone={profitTone} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Sharpe ratio" value={result.sharpeRatio?.toFixed(2) ?? "—"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}>
        <Metric label="Buy & hold" value={`${(result.benchmarkReturnPercent ?? 0).toFixed(2)}%`} />
      </Grid>
      <Grid size={{ xs: 12, lg: 6 }}><Metric label="Период бэктеста" value={period} /></Grid>
    </Grid>
    <Alert severity="info" sx={{ mt: 1.5 }}>
      Только закрытые свечи · ТФ: {result.dataset?.timeframes.join(", ") ?? "—"} · свечей теста: {result.dataset?.testCandles ?? 0}
      {" · "}режим: фиксированный алгоритм
    </Alert>
    {result.optimization && <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
      <Typography variant="h6">Результат автоматического подбора</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: .5, mb: 1.5 }}>
        Проверено комбинаций: {result.optimization.testedCombinations}; на валидацию прошли: {result.optimization.validatedCandidates}.
      </Typography>
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: .75, mb: 1.5 }}>
        {Object.entries(result.optimization.bestParameters).map(([key, value]) =>
          <Chip key={key} color="primary" variant="outlined" label={`${key}: ${String(value)}`} />)}
      </Stack>
      <TableContainer><Table size="small">
        <TableHead><TableRow><TableCell>Место</TableCell><TableCell>Score</TableCell><TableCell>Доходность</TableCell>
          <TableCell>Просадка</TableCell><TableCell>Сделок</TableCell><TableCell>Win rate</TableCell><TableCell>Параметры</TableCell></TableRow></TableHead>
        <TableBody>{result.optimization.validationLeaderboard.map((candidate, index) => <TableRow key={index}>
          <TableCell>{index + 1}</TableCell><TableCell>{candidate.score?.toFixed(2) ?? "—"}</TableCell>
          <TableCell>{candidate.totalReturnPercent.toFixed(2)}%</TableCell><TableCell>{candidate.maxDrawdownPercent.toFixed(2)}%</TableCell>
          <TableCell>{candidate.totalTrades}</TableCell><TableCell>{candidate.winRate.toFixed(1)}%</TableCell>
          <TableCell>{Object.entries(candidate.parameters).map(([key, value]) => `${key}=${String(value)}`).join(", ")}</TableCell>
        </TableRow>)}</TableBody>
      </Table></TableContainer>
    </Paper>}
    <EquityChart points={result.equity} />
    <BacktestPriceChart
      candles={result.chartCandles}
      candlesByTimeframe={result.chartCandlesByTimeframe}
      overlaysByTimeframe={result.structureOverlaysByTimeframe}
      scenarios={result.scenarios}
      trades={result.trades}
    />
    <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>Распределение по шаблонам</Typography>
      <Stack spacing={1}>{Object.entries(result.templateDistribution ?? {}).map(([templateId, item]) => (
        <Typography key={templateId} variant="body2">
          {templateId}: {item.trades} сделок · {item.wins} прибыльных · PnL {item.pnl.toFixed(2)}
        </Typography>
      ))}</Stack>
      {!Object.keys(result.templateDistribution ?? {}).length && <Typography color="text.secondary">Сделок по шаблонам нет.</Typography>}
    </Paper>
    <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
      <Typography variant="h6" sx={{ mb: 1.5 }}>Диагностика поиска паттернов</Typography>
      {Object.entries(result.patternDiagnostics).map(([template, reasons]) => {
        const maximum = Math.max(1,...Object.values(reasons));
        return <Paper key={template} variant="outlined" sx={{ p: 1.5, mb: 1 }}>
          <Typography variant="subtitle2">{template}</Typography>
          {Object.entries(reasons).sort((left,right) => right[1]-left[1]).map(([reason,count]) => {
            const explanation = diagnosticLabels[reason] ?? { title: reason, hint: "Условие шаблона не выполнено." };
            return <Box key={reason} sx={{ mt: 1 }}>
              <Stack direction="row" sx={{ justifyContent: "space-between", gap: 1 }}>
                <Typography variant="body2">{explanation.title}</Typography><Typography variant="body2" sx={{ fontWeight: 700 }}>{count}</Typography>
              </Stack>
              <LinearProgress variant="determinate" value={count/maximum*100} sx={{ my: .5 }} />
              <Typography variant="caption" color="text.secondary">{explanation.hint}</Typography>
            </Box>;
          })}
        </Paper>;
      })}
      {!Object.keys(result.patternDiagnostics).length && <Typography color="text.secondary">Диагностика отсутствует.</Typography>}
    </Paper>
    <Paper variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
      <Stack direction={{ xs: "column", sm: "row" }} sx={{ px: 1, pb: 2, alignItems: { sm: "center" }, justifyContent: "space-between", gap: 1 }}>
        <div><Typography variant="h6">Журнал сделок</Typography>
          <Typography variant="caption" color="text.secondary">Период определяется по дате фиксации результата сделки.</Typography></div>
        <TextField select size="small" label="Период" value={tradePeriod} sx={{ minWidth: 220 }}
          onChange={(event) => { setTradePeriod(event.target.value); setTradePage(0); }}>
          <MenuItem value="ALL">Весь период</MenuItem>
          <ListSubheader>По месяцам</ListSubheader>
          {months.map((key) => <MenuItem key={`M:${key}`} value={`M:${key}`}>{monthLabel(key)}</MenuItem>)}
          <ListSubheader>По кварталам</ListSubheader>
          {quarters.map((key) => <MenuItem key={`Q:${key}`} value={`Q:${key}`}>{key.replace("-Q", " · Q")}</MenuItem>)}
        </TextField>
      </Stack>
      <TableContainer><Table size="small">
        <TableHead><TableRow><TableCell>#</TableCell><TableCell>Вход</TableCell><TableCell>Выход</TableCell><TableCell>Сторона</TableCell>
          <TableCell>Цена входа</TableCell><TableCell>Цена выхода</TableCell><TableCell>Количество</TableCell><TableCell>Общая цена лота</TableCell>
          <TableCell>Маржа</TableCell><TableCell>Тейк, %</TableCell><TableCell>Стоп, %</TableCell>
          <TableCell>PnL</TableCell><TableCell>Прибыль, %</TableCell><TableCell>Причина</TableCell>
        </TableRow></TableHead>
        <TableBody>{visibleTrades.map((trade) => {
          const scenario = trade.scenarioId ? scenariosById.get(trade.scenarioId) : undefined;
          const takePercents = scenario?.takeProfitPrices.map((price) => Math.abs(price-trade.entryPrice)/trade.entryPrice*100);
          const stopPercent = scenario
            ? Math.abs(scenario.stopLossPrice-trade.entryPrice)/trade.entryPrice*100
            : result.strategyConfig?.stopLossPercent;
          const fallbackTake = result.strategyConfig?.takeProfitPercent;
          return <TableRow key={trade.id}>
          <TableCell>{trade.id}</TableCell><TableCell>{new Date(trade.entryTime).toLocaleString("ru-RU")}</TableCell>
          <TableCell>{new Date(trade.exitTime).toLocaleString("ru-RU")}</TableCell><TableCell>{trade.direction}</TableCell>
          <TableCell>{trade.entryPrice.toFixed(2)}</TableCell><TableCell>{trade.exitPrice.toFixed(2)}</TableCell>
          <TableCell>{trade.quantity.toFixed(6)}</TableCell>
          <TableCell>{(trade.entryPrice*trade.quantity).toFixed(2)}</TableCell>
          <TableCell>{marginValue(trade,leverage).toFixed(2)}</TableCell>
          <TableCell>{takePercents?.length
            ? takePercents.map((value) => `${value.toFixed(2)}%`).join(" / ")
            : fallbackTake === undefined ? "—" : `${fallbackTake.toFixed(2)}%`}</TableCell>
          <TableCell>{stopPercent === undefined ? "—" : `${stopPercent.toFixed(2)}%`}</TableCell>
          <TableCell sx={{ color: trade.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{trade.pnl.toFixed(2)}</TableCell>
          <TableCell sx={{ color: trade.pnlPercent >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>
            {trade.pnlPercent.toFixed(2)}%
          </TableCell>
          <TableCell><Chip size="small" label={trade.reason} variant="outlined" /></TableCell>
        </TableRow>})}</TableBody>
      </Table></TableContainer>
      <TablePagination component="div" count={filteredTrades.length} page={tradePage} rowsPerPage={tradesPerPage}
        onPageChange={(_,value) => setTradePage(value)}
        onRowsPerPageChange={(event) => { setTradesPerPage(Number(event.target.value)); setTradePage(0); }}
        rowsPerPageOptions={[5,10,25,50]} labelRowsPerPage="Сделок на странице" />
    </Paper>
    {(["months","quarters"] as const).map((periodType) => <Paper key={periodType} variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
      <Typography variant="h6" sx={{ px: 1, pb: 2 }}>Метрики по {periodType === "months" ? "месяцам" : "кварталам"}</Typography>
      <TableContainer><Table size="small">
        <TableHead><TableRow><TableCell>Период</TableCell><TableCell>Сделок</TableCell><TableCell>Win rate</TableCell>
          <TableCell>PnL</TableCell><TableCell>Доходность от начального капитала</TableCell>
          <TableCell>Оборот лотов</TableCell><TableCell>Использовано маржи</TableCell></TableRow></TableHead>
        <TableBody>{periodicMetrics[periodType].map((item) => <TableRow key={item.key}>
          <TableCell sx={{ textTransform: "capitalize" }}>{item.label}</TableCell><TableCell>{item.trades}</TableCell>
          <TableCell>{item.trades ? (item.wins/item.trades*100).toFixed(1) : "0.0"}%</TableCell>
          <TableCell sx={{ color: item.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{item.pnl.toFixed(2)}</TableCell>
          <TableCell>{item.returnPercent.toFixed(2)}%</TableCell><TableCell>{item.notional.toFixed(2)}</TableCell>
          <TableCell>{item.margin.toFixed(2)}</TableCell>
        </TableRow>)}</TableBody>
      </Table></TableContainer>
      {!periodicMetrics[periodType].length && <Typography color="text.secondary" sx={{ p: 1 }}>Нет закрытых сделок.</Typography>}
    </Paper>)}
  </>;
}
