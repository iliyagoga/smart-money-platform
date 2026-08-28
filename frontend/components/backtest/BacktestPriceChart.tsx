"use client";

import { Box, Button, Chip, CircularProgress, FormControlLabel, MenuItem, Pagination, Paper, Stack, Switch, TextField, Typography } from "@mui/material";
import { BaselineSeries, CandlestickSeries, ColorType, LineSeries, createChart, createSeriesMarkers, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BacktestChartCandle, BacktestScenario, BacktestTrade, ElliottPattern } from "../../lib/backtest/types";

const chartTime = (timestamp: number) => Math.floor(timestamp/1000) as UTCTimestamp;

export function BacktestPriceChart({ candles, candlesByTimeframe, elliottPatterns, scenarios, trades }: {
  candles: BacktestChartCandle[];
  candlesByTimeframe: Record<string, BacktestChartCandle[]>;
  scenarios: BacktestScenario[];
  trades: BacktestTrade[];
  elliottPatterns: ElliottPattern[];
}) {
  const available = Object.keys(candlesByTimeframe);
  const [timeframe, setTimeframe] = useState(available[0] ?? "PRIMARY");
  const [selectedScenario, setSelectedScenario] = useState("ALL");
  const [direction, setDirection] = useState<"ALL" | "LONG" | "SHORT">("ALL");
  const [visibleTemplates, setVisibleTemplates] = useState<string[]>([]);
  const [zoneLimit, setZoneLimit] = useState(100);
  const [zonePage, setZonePage] = useState(1);
  const [showEntryZones, setShowEntryZones] = useState(true);
  const [showStops, setShowStops] = useState(true);
  const [showTargets, setShowTargets] = useState(true);
  const [showTrades, setShowTrades] = useState(true);
  const [showWaves, setShowWaves] = useState(true);
  const [isRendering, setIsRendering] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fitRef = useRef<(scenario?: BacktestScenario) => void>(() => undefined);
  const visibleRangeRef = useRef<ReturnType<IChartApi["timeScale"]>["getVisibleRange"] extends () => infer R ? R : never>(null);
  const selectedCandles = candlesByTimeframe[timeframe] ?? candles;
  const timeframeScenarios = useMemo(
    () => available.length ? scenarios.filter((item) => item.timeframe === timeframe) : scenarios,
    [available.length, scenarios, timeframe],
  );
  const templates = useMemo(() => [...new Set(timeframeScenarios.map((item) => item.templateId))].sort(), [timeframeScenarios]);
  const filteredScenarios = useMemo(() => timeframeScenarios.filter((item) =>
    (direction === "ALL" || item.direction === direction)
    && (!visibleTemplates.length || visibleTemplates.includes(item.templateId))),
  [direction, timeframeScenarios, visibleTemplates]);
  const visibleScenarios = useMemo(() => {
    const selected = filteredScenarios.find((item) => item.id === selectedScenario);
    const pageStart = Math.max(0, filteredScenarios.length-zonePage*zoneLimit);
    const window = filteredScenarios.slice(pageStart, pageStart+zoneLimit);
    return selected && !window.some((item) => item.id === selected.id) ? [...window.slice(1), selected] : window;
  }, [filteredScenarios, selectedScenario, zoneLimit, zonePage]);
  const zonePageCount = Math.max(1,Math.ceil(filteredScenarios.length/zoneLimit));

  useEffect(() => {
    setVisibleTemplates((current) => current.filter((item) => templates.includes(item)));
  }, [templates]);
  useEffect(() => setZonePage(1), [direction, timeframe, visibleTemplates, zoneLimit]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !selectedCandles.length) return;
    setIsRendering(true);
    let chart: IChartApi | undefined;
    let observer: ResizeObserver | undefined;
    const frame = requestAnimationFrame(() => {
    const activeChart = createChart(container, {
      width: container.clientWidth, height: 620,
      layout: { background: { type: ColorType.Solid, color: "#101722" }, textColor: "#b2b9c6", attributionLogo: true },
      grid: { vertLines: { color: "#1e2938" }, horzLines: { color: "#1e2938" } },
      crosshair: { vertLine: { labelBackgroundColor: "#2962ff" }, horzLine: { labelBackgroundColor: "#2962ff" } },
      rightPriceScale: { borderColor: "#334155", autoScale: true },
      timeScale: { borderColor: "#334155", timeVisible: true, secondsVisible: false, rightOffset: 8 },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });
    chart = activeChart;
    const candleSeries = activeChart.addSeries(CandlestickSeries, {
      upColor: "#26a69a", downColor: "#ef5350", wickUpColor: "#26a69a", wickDownColor: "#ef5350",
      borderVisible: false,
    });
    candleSeries.setData(selectedCandles.map((item) => ({
      time: chartTime(item.timestamp), open: item.open, high: item.high, low: item.low, close: item.close,
    })));
    if (showWaves) elliottPatterns.filter((pattern) => pattern.state !== "INVALID").forEach((pattern) => {
      const order = ["P0", "P1", "P2", "P3", "P4", "P5", "A", "B", "C"];
      const points = order.flatMap((label) => pattern.points[label] ? [{ label, ...pattern.points[label] }] : []);
      if (points.length < 2) return;
      const wave = activeChart.addSeries(LineSeries, {
        color: pattern.direction === "LONG" ? "#42a5f5" : "#ab47bc", lineWidth: 2,
        title: `Elliott ${pattern.structureTimeframe}`,
      });
      wave.setData(points.map((point) => ({ time: chartTime(nearestTimestamp(selectedCandles, point.timestamp)), value: point.price })));
    });
    visibleScenarios.forEach((scenario) => {
      const color = scenario.direction === "LONG" ? "#26a69a" : "#ef5350";
      const end = Math.min(scenario.expiresAt, selectedCandles[selectedCandles.length-1].timestamp);
      if (showEntryZones) {
        const zoneHigh = activeChart.addSeries(LineSeries, { color, lineWidth: 2, title: `${scenario.templateId} zone` });
        const zoneLow = activeChart.addSeries(LineSeries, { color, lineWidth: 2, title: "" });
        zoneHigh.setData([
          { time: chartTime(scenario.timestamp), value: scenario.entryZoneHigh },
          { time: chartTime(end), value: scenario.entryZoneHigh },
        ]);
        zoneLow.setData([
          { time: chartTime(scenario.timestamp), value: scenario.entryZoneLow },
          { time: chartTime(end), value: scenario.entryZoneLow },
        ]);
      }
      if (showStops) {
        const stop = activeChart.addSeries(LineSeries, { color: "#ff5252", lineWidth: 1, lineStyle: 2, title: "SL" });
        stop.setData([
          { time: chartTime(scenario.timestamp), value: scenario.stopLossPrice },
          { time: chartTime(end), value: scenario.stopLossPrice },
        ]);
      }
      if (showTargets) scenario.takeProfitPrices.forEach((target, index) => {
        const takeProfit = activeChart.addSeries(LineSeries, {
          color: "#00c853", lineWidth: 1, lineStyle: 2, title: `TP${index+1}`,
        });
        takeProfit.setData([{ time: chartTime(scenario.timestamp), value: target }, { time: chartTime(end), value: target }]);
      });
    });
    if (showTrades) trades.forEach((trade) => {
      const targets = trade.takeProfitPrices ?? [];
      const stop = trade.initialStop;
      const entryTimestamp = nearestTimestamp(selectedCandles, trade.entryTime);
      const exitTimestamp = nearestTimestamp(selectedCandles, trade.exitTime);
      const tradeCandles = selectedCandles.filter((item) => item.timestamp >= trade.entryTime && item.timestamp <= trade.exitTime);
      const reached = tradeCandles.length
        ? (trade.direction === "LONG" ? Math.max(...tradeCandles.map((item) => item.high)) : Math.min(...tradeCandles.map((item) => item.low)))
        : trade.exitPrice;
      targets.forEach((target, index) => {
        const targetZone = activeChart.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: trade.entryPrice }, lineVisible: false,
          topFillColor1: "rgba(0,200,83,.18)", topFillColor2: "rgba(0,200,83,.04)",
          bottomFillColor1: "rgba(0,200,83,.18)", bottomFillColor2: "rgba(0,200,83,.04)",
          priceLineVisible: false, lastValueVisible: false, title: `TP${index + 1} · ${trade.signalTimeframe ?? "—"}`,
        });
        targetZone.setData([{ time: chartTime(entryTimestamp), value: target }, { time: chartTime(exitTimestamp), value: target }]);
      });
      if (tradeCandles.length && trade.direction && Math.abs(reached - trade.entryPrice) > 1e-9) {
        const reachedZone = activeChart.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: trade.entryPrice }, lineVisible: false,
          topFillColor1: "rgba(144,238,144,.42)", topFillColor2: "rgba(144,238,144,.16)",
          bottomFillColor1: "rgba(144,238,144,.42)", bottomFillColor2: "rgba(144,238,144,.16)",
          priceLineVisible: false, lastValueVisible: false, title: "Фактически достигнуто",
        });
        reachedZone.setData([{ time: chartTime(entryTimestamp), value: reached }, { time: chartTime(exitTimestamp), value: reached }]);
      }
      if (stop !== undefined) {
        const stopZone = activeChart.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: trade.entryPrice }, lineVisible: false,
          topFillColor1: "rgba(255,82,82,.24)", topFillColor2: "rgba(255,82,82,.08)",
          bottomFillColor1: "rgba(255,82,82,.24)", bottomFillColor2: "rgba(255,82,82,.08)",
          priceLineVisible: false, lastValueVisible: false, title: "SL",
        });
        stopZone.setData([
          { time: chartTime(entryTimestamp), value: stop },
          { time: chartTime(exitTimestamp), value: stop },
        ]);
      }
    });
    const tradeMarkers = showTrades ? trades.flatMap((trade) => [
      { time: chartTime(trade.entryTime), position: trade.direction === "LONG" ? "belowBar" as const : "aboveBar" as const,
        color: trade.direction === "LONG" ? "#00e676" : "#ff5252", shape: trade.direction === "LONG" ? "arrowUp" as const : "arrowDown" as const,
        text: `${trade.direction} #${trade.id} · ${trade.signalTimeframe ?? "—"}` },
      { time: chartTime(trade.exitTime), position: "inBar" as const, color: trade.pnl >= 0 ? "#ffd54f" : "#ff9800",
        shape: "circle" as const, text: `Exit ${trade.pnl.toFixed(2)}` },
    ]) : [];
    const waveMarkers = showWaves ? elliottPatterns.filter((pattern) => pattern.state !== "INVALID").flatMap((pattern) =>
      Object.entries(pattern.points).map(([label, point]) => ({
        time: chartTime(nearestTimestamp(selectedCandles, point.timestamp)),
        position: point.kind === "LOW" ? "belowBar" as const : "aboveBar" as const,
        color: pattern.direction === "LONG" ? "#42a5f5" : "#ab47bc", shape: "circle" as const,
        text: `${label} · ${pattern.structureTimeframe}`,
      }))) : [];
    const markers = [...tradeMarkers, ...waveMarkers].sort((left,right) => Number(left.time)-Number(right.time));
    createSeriesMarkers(candleSeries, markers);
    if (visibleRangeRef.current) activeChart.timeScale().setVisibleRange(visibleRangeRef.current);
    else activeChart.timeScale().fitContent();
    activeChart.timeScale().subscribeVisibleTimeRangeChange((range) => { if (range) visibleRangeRef.current = range; });
    fitRef.current = (scenario) => scenario
      ? activeChart.timeScale().setVisibleRange({ from: chartTime(scenario.timestamp), to: chartTime(scenario.expiresAt) })
      : activeChart.timeScale().fitContent();
    observer = new ResizeObserver(() => chart?.applyOptions({ width: container.clientWidth }));
    observer.observe(container);
    setIsRendering(false);
    fitRef.current(selectedScenario === "ALL" ? undefined : visibleScenarios.find((item) => item.id === selectedScenario));
    });
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      chart?.remove();
    };
  }, [elliottPatterns, selectedCandles, selectedScenario, showEntryZones, showStops, showTargets, showTrades, showWaves, trades, visibleScenarios]);

  const focusScenario = () => {
    const scenario = visibleScenarios.find((item) => item.id === selectedScenario);
    fitRef.current(scenario);
  };
  const toggleFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await fullscreenRef.current?.requestFullscreen();
  };
  useEffect(() => {
    const update = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange",update);
    return () => document.removeEventListener("fullscreenchange",update);
  },[]);

  return <Paper ref={fullscreenRef} variant="outlined" sx={{
    mt: 1.5, p: 2,
    "&:fullscreen": { bgcolor: "background.default", p: 2, overflow: "auto" },
  }}>
    <Stack direction={{ xs: "column", lg: "row" }} sx={{ justifyContent: "space-between", gap: 1.5, mb: 1.5 }}>
      <div><Typography variant="h6">TradingView Lightweight Charts</Typography>
        <Typography variant="caption" color="text.secondary">
          Колесо мыши — масштаб, перетаскивание — навигация, шкала цены — вертикальное увеличение.
        </Typography></div>
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: .75 }}>
        {available.length > 0 && <TextField select size="small" label="Таймфрейм" value={timeframe}
          onChange={(event) => { visibleRangeRef.current = null; setIsRendering(true); setTimeframe(event.target.value); setSelectedScenario("ALL"); }} sx={{ minWidth: 125 }}>
          {available.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>}
        <TextField select size="small" label="Зона" value={selectedScenario}
          onChange={(event) => setSelectedScenario(event.target.value)} sx={{ minWidth: 230 }}>
          <MenuItem value="ALL">Все зоны</MenuItem>
          {filteredScenarios.map((item) => <MenuItem key={item.id} value={item.id}>
            {item.templateId} · {item.direction} · {(item.confidence*100).toFixed(0)}%
          </MenuItem>)}
        </TextField>
        <Button variant="outlined" onClick={focusScenario}>Показать</Button>
        <Button variant="outlined" onClick={() => fitRef.current()}>Весь период</Button>
        <Button variant="contained" onClick={() => void toggleFullscreen()}>
          {isFullscreen ? "Выйти из полного экрана" : "На весь экран"}
        </Button>
      </Stack>
    </Stack>
    <Paper variant="outlined" sx={{ mb: 1.5, p: 1.25, bgcolor: "action.hover" }}>
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
        <Typography variant="body2" sx={{ fontWeight: 700 }}>Фильтры:</Typography>
        {(["ALL","LONG","SHORT"] as const).map((item) => <Chip key={item} clickable size="small"
          color={direction === item ? (item === "SHORT" ? "error" : item === "LONG" ? "success" : "primary") : "default"}
          variant={direction === item ? "filled" : "outlined"} label={item === "ALL" ? "Все направления" : item}
          onClick={() => { setDirection(item); setSelectedScenario("ALL"); }} />)}
        {templates.map((template) => {
          const enabled = !visibleTemplates.length || visibleTemplates.includes(template);
          return <Chip key={template} clickable size="small" label={template} color={enabled ? "primary" : "default"}
            variant={enabled ? "filled" : "outlined"} onClick={() => setVisibleTemplates((current) => {
              const active = current.length ? current : templates;
              const next = active.includes(template) ? active.filter((item) => item !== template) : [...active,template];
              return next.length === templates.length ? [] : next;
            })} />;
        })}
        <Button size="small" onClick={() => setVisibleTemplates([])}>Все шаблоны</Button>
      </Stack>
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", gap: .5, mt: 1 }}>
        <FormControlLabel control={<Switch size="small" checked={showEntryZones} onChange={(_,value) => setShowEntryZones(value)} />} label="Зоны входа" />
        <FormControlLabel control={<Switch size="small" checked={showStops} onChange={(_,value) => setShowStops(value)} />} label="Stop Loss" />
        <FormControlLabel control={<Switch size="small" checked={showTargets} onChange={(_,value) => setShowTargets(value)} />} label="Take Profit" />
        <FormControlLabel control={<Switch size="small" checked={showTrades} onChange={(_,value) => setShowTrades(value)} />} label="Сделки" />
        <FormControlLabel control={<Switch size="small" checked={showWaves} onChange={(_,value) => setShowWaves(value)} />} label="Волны Elliott" />
        <TextField select size="small" label="Зон на графике" value={zoneLimit} onChange={(event) => setZoneLimit(Number(event.target.value))} sx={{ width: 150 }}>
          {[25,50,100,200].map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>
      </Stack>
      {zonePageCount > 1 && <Stack direction={{ xs: "column", sm: "row" }} sx={{ alignItems: { sm: "center" }, gap: 1, mt: 1 }}>
        <Typography variant="caption" color="text.secondary">Окно зон: 1 — самые новые</Typography>
        <Pagination size="small" count={zonePageCount} page={zonePage} onChange={(_,value) => { setIsRendering(true); setZonePage(value); }}
          siblingCount={1} boundaryCount={1} color="primary" />
      </Stack>}
    </Paper>
    <Stack direction="row" spacing={.75} sx={{ mb: 1 }}><Chip size="small" color="success" label="Long" />
      <Chip size="small" color="error" label="Short" /><Chip size="small" label={`${filteredScenarios.length} найдено · ${visibleScenarios.length} показано`} />
      <Chip size="small" label={`${trades.length} сделок`} /></Stack>
    <Box sx={{ position: "relative" }}>
      <Box ref={containerRef} sx={{ width: "100%", minHeight: 620, borderRadius: 1, overflow: "hidden" }} />
      {isRendering && <Stack sx={{ position: "absolute", inset: 0, alignItems: "center", justifyContent: "center", bgcolor: "rgba(16,23,34,.72)", zIndex: 2 }}>
        <CircularProgress size={32} /><Typography variant="body2" sx={{ mt: 1 }}>Строим график {timeframe}…</Typography>
      </Stack>}
    </Box>
    <Typography variant="caption" color="text.secondary">
      График создан с помощью <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a>.
    </Typography>
  </Paper>;
}

function nearestTimestamp(candles: BacktestChartCandle[], timestamp: number) {
  if (!candles.length) return timestamp;
  let left = 0, right = candles.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (candles[middle].timestamp < timestamp) left = middle + 1; else right = middle;
  }
  const previousIsNearer = left > 0
    && Math.abs(candles[left - 1].timestamp - timestamp) < Math.abs(candles[left].timestamp - timestamp);
  if (previousIsNearer) return candles[left - 1].timestamp;
  return candles[left].timestamp;
}
