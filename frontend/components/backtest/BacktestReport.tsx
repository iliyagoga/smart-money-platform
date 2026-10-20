"use client";

import { Alert, Chip, Grid, ListSubheader, MenuItem, Paper, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import type { BacktestResult, BacktestTrade } from "../../lib/backtest/types";
import { EquityChart } from "./EquityChart";
import { BacktestPriceChart } from "./BacktestPriceChart";

interface MetricProps { label: string; value: string; tone?: "success" | "error" }

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
  const effectiveLeverage = trade.leverage ?? leverage;
  if (effectiveLeverage) return notional/effectiveLeverage;
  return Math.abs(trade.pnlPercent) > 1e-12 ? Math.abs(trade.pnl/(trade.pnlPercent/100)) : notional;
};
const summarize = (trades: BacktestTrade[], initialCapital: number, leverage?: number) => ({
  trades: trades.length,
  wins: trades.filter((trade) => trade.pnl > 0).length,
  losses: trades.filter((trade) => trade.pnl < 0).length,
  averageLoss: (() => {
    const losses = trades.filter((trade) => trade.pnl < 0);
    return losses.length ? losses.reduce((sum, trade) => sum + trade.pnl, 0) / losses.length : 0;
  })(),
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
    {result.portfolio && <Paper variant="outlined" sx={{ p: 2.5, mb: 2 }}>
      <Typography variant="h6">Портфель «{result.portfolio.name}» · вклад активов</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ my: 1 }}>
        {result.portfolio.capital_mode === "SEQUENTIAL"
          ? `Последовательный режим: одновременно открыта одна сделка; размер каждой позиции рассчитан от актуального капитала. Пересекающихся сделок пропущено: ${result.portfolio.skipped_overlapping_trades ?? 0}. `
          : `Свободные средства: ${result.portfolio.cash.toFixed(2)}. Капитал распределён при старте, без перераспределения между активами. `}
        Вклад в доходность — PnL актива / стартовый капитал портфеля; сумма вкладов равна доходности портфеля.
        Просадка рассчитана по общей кривой капитала на временных отметках свечей. Sharpe — по дневной доходности (365 дней).
      </Typography>
      <TableContainer><Table size="small"><TableHead><TableRow>
        {["Актив", "Доля", result.portfolio.capital_mode === "SEQUENTIAL" ? "База капитала" : "Стартовый капитал", "Итоговый капитал", "PnL", "Доходность актива",
          "Вклад, п.п.", "Сделок", "Win rate", "Просадка актива"].map(label => <TableCell key={label}>{label}</TableCell>)}
        {result.portfolio.capital_mode === "SEQUENTIAL" && <TableCell>Пропущено</TableCell>}
      </TableRow></TableHead><TableBody>{result.portfolio.assets.map(asset => <TableRow key={asset.symbol}>
        <TableCell>{asset.symbol}</TableCell><TableCell>{asset.allocation_percent.toFixed(2)}%</TableCell>
        <TableCell>{asset.initial_capital.toFixed(2)}</TableCell><TableCell>{asset.final_capital.toFixed(2)}</TableCell>
        <TableCell sx={{ color: asset.net_profit >= 0 ? "success.main" : "error.main" }}>{asset.net_profit.toFixed(2)}</TableCell>
        <TableCell>{asset.total_return_percent.toFixed(2)}%</TableCell><TableCell>{asset.contribution_percent.toFixed(2)}</TableCell>
        <TableCell>{asset.total_trades}</TableCell><TableCell>{asset.win_rate.toFixed(1)}%</TableCell>
        <TableCell>{asset.max_drawdown_percent.toFixed(2)}%</TableCell>
        {result.portfolio?.capital_mode === "SEQUENTIAL" && <TableCell>{asset.skipped_trades ?? 0}</TableCell>}
      </TableRow>)}</TableBody></Table></TableContainer>
    </Paper>}
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
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Среднемесячная доходность" value={`${result.averageMonthlyReturnPercent.toFixed(2)}%`} tone={result.averageMonthlyReturnPercent >= 0 ? "success" : "error"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Среднегодовая доходность (CAGR)" value={`${result.annualizedReturnPercent.toFixed(2)}%`} tone={result.annualizedReturnPercent >= 0 ? "success" : "error"} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Убыточные месяцы" value={`${result.losingMonths} · ${result.losingMonthsPercent.toFixed(1)}%`} tone="error" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Средний убыток месяца" value={`${result.averageLosingMonthPercent.toFixed(2)}%`} tone="error" /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Стабильность equity (R²)" value={result.equityCurveRSquared.toFixed(3)} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}><Metric label="Recovery factor" value={result.recoveryFactor?.toFixed(2) ?? "—"} tone={result.recoveryFactor !== undefined && result.recoveryFactor < 0 ? "error" : undefined} /></Grid>
      <Grid size={{ xs: 6, lg: 3 }}>
        <Metric label="Buy & hold" value={`${(result.benchmarkReturnPercent ?? 0).toFixed(2)}%`} />
      </Grid>
      <Grid size={{ xs: 12, lg: 6 }}><Metric label="Период бэктеста" value={period} /></Grid>
    </Grid>
    <Alert severity="info" sx={{ mt: 1.5 }}>
      Только закрытые свечи · ТФ: {result.dataset?.timeframes.join(", ") ?? "—"} · свечей теста: {result.dataset?.testCandles ?? 0}
    </Alert>
    <EquityChart points={result.equity} />
    {!result.portfolio && <BacktestPriceChart
      candles={result.chartCandles}
      candlesByTimeframe={result.chartCandlesByTimeframe}

      trades={result.trades}
      elliottPatterns={result.elliottPatterns}
      elliottConfig={result.elliottConfig}
    />}
    {result.elliottDiagnostics && <Alert severity="success" sx={{ mt: 1.5 }}>
      Elliott: {result.elliottDiagnostics.patterns} кандидатов · {result.elliottDiagnostics.signals} сигналов
      {" · "}{result.elliottDiagnostics.tradedSignals} обработано
      {" · "}close-time replay: {result.elliottDiagnostics.lookaheadSafe ? "без look-ahead" : "не подтверждено"}
      {" · "}{Object.entries(result.elliottDiagnostics.states).map(([state, count]) => `${state}: ${count}`).join("; ")}
      {result.elliottDiagnostics.riskPerTradePercent !== undefined
        ? result.elliottDiagnostics.riskPerTradePercent === 0
          ? " · риск-сайзинг отключён"
          : ` · риск-сайзинг: ${result.elliottDiagnostics.riskPerTradePercent}% до стопа`
        : ""}
    </Alert>}
    {result.elliottDiagnostics?.selectionBiasWarning && <Alert severity="warning" sx={{ mt: 1.5 }}>
      После подбора параметров оценивайте результат на отдельном, ранее не просмотренном периоде.
    </Alert>}
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
        <TableHead><TableRow><TableCell>#</TableCell>{result.portfolio && <TableCell>Актив</TableCell>}
          {result.portfolio?.capital_mode === "SEQUENTIAL" && <><TableCell>Капитал до сделки</TableCell><TableCell>Доля в сделке</TableCell></>}
          <TableCell>Вход</TableCell><TableCell>Выход</TableCell><TableCell>Сторона</TableCell>
          <TableCell>Цена входа</TableCell><TableCell>Цена выхода</TableCell><TableCell>Количество</TableCell><TableCell>Общая цена лота</TableCell>
          <TableCell>Маржа</TableCell><TableCell>Тейк, %</TableCell><TableCell>Стоп, %</TableCell>
          <TableCell>Исполнение</TableCell><TableCell>PnL</TableCell><TableCell>Прибыль, %</TableCell><TableCell>Причина</TableCell>
        </TableRow></TableHead>
        <TableBody>{visibleTrades.map((trade) => {
          const takePrices = trade.takeProfitPrices;
          const takePercents = takePrices?.map((price) => Math.abs(price-trade.entryPrice)/trade.entryPrice*100);
          const stopPercent = trade.initialStop !== undefined
            ? Math.abs(trade.initialStop-trade.entryPrice)/trade.entryPrice*100
            : undefined;
          return <TableRow key={trade.id}>
          <TableCell>{trade.id}</TableCell>{result.portfolio && <TableCell>{trade.symbol}</TableCell>}
          {result.portfolio?.capital_mode === "SEQUENTIAL" && <><TableCell>{trade.capitalBefore?.toFixed(2) ?? "—"}</TableCell><TableCell>{trade.allocatedCapital?.toFixed(2) ?? "—"} ({trade.allocationPercent?.toFixed(2) ?? "—"}%)</TableCell></>}
          <TableCell>{new Date(trade.entryTime).toLocaleString("ru-RU")}</TableCell>
          <TableCell>{new Date(trade.exitTime).toLocaleString("ru-RU")}</TableCell><TableCell>{trade.direction}</TableCell>
          <TableCell>{trade.entryPrice.toFixed(2)}</TableCell><TableCell>{trade.exitPrice.toFixed(2)}</TableCell>
          <TableCell>{trade.quantity.toFixed(6)}</TableCell>
          <TableCell>{(trade.entryPrice*trade.quantity).toFixed(2)}</TableCell>
          <TableCell>{marginValue(trade,leverage).toFixed(2)}</TableCell>
          <TableCell>{takePercents?.length
            ? takePercents.map((value) => `${value.toFixed(2)}%`).join(" / ")
            : "—"}</TableCell>
          <TableCell>{stopPercent === undefined ? "—" : `${stopPercent.toFixed(2)}%`}</TableCell>
          <TableCell>{trade.exits?.length
            ? trade.exits.map((exit, index) => `${index + 1}. ${exit.reason} · ${exit.quantity.toFixed(2)} @ ${exit.price.toFixed(4)} · ${exit.pnl >= 0 ? "+" : ""}${exit.pnl.toFixed(2)}`).join(" / ")
            : "—"}</TableCell>
          <TableCell sx={{ color: trade.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{trade.pnl.toFixed(2)}</TableCell>
          <TableCell sx={{ color: trade.pnlPercent >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>
            {trade.pnlPercent.toFixed(2)}%
          </TableCell>
          <TableCell><Chip size="small" label={`${trade.reason}${trade.fees ? ` · fee ${trade.fees.toFixed(2)}` : ""}`} variant="outlined" /></TableCell>
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
          <TableCell>Убыточных сделок</TableCell><TableCell>Средний убыток</TableCell>
          <TableCell>PnL</TableCell><TableCell>Доходность от начального капитала</TableCell>
          <TableCell>Оборот лотов</TableCell><TableCell>Использовано маржи</TableCell></TableRow></TableHead>
        <TableBody>{periodicMetrics[periodType].map((item) => <TableRow key={item.key}>
          <TableCell sx={{ textTransform: "capitalize" }}>{item.label}</TableCell><TableCell>{item.trades}</TableCell>
          <TableCell>{item.trades ? (item.wins/item.trades*100).toFixed(1) : "0.0"}%</TableCell>
          <TableCell>{item.losses}</TableCell>
          <TableCell sx={{ color: item.averageLoss < 0 ? "error.main" : "text.primary" }}>
            {item.losses ? item.averageLoss.toFixed(2) : "—"}
          </TableCell>
          <TableCell sx={{ color: item.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{item.pnl.toFixed(2)}</TableCell>
          <TableCell>{item.returnPercent.toFixed(2)}%</TableCell><TableCell>{item.notional.toFixed(2)}</TableCell>
          <TableCell>{item.margin.toFixed(2)}</TableCell>
        </TableRow>)}</TableBody>
      </Table></TableContainer>
      {!periodicMetrics[periodType].length && <Typography color="text.secondary" sx={{ p: 1 }}>Нет закрытых сделок.</Typography>}
    </Paper>)}
  </>;
}
