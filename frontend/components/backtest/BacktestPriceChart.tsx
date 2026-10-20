"use client";

import { Box, Button, Chip, CircularProgress, FormControlLabel, MenuItem, Paper, Stack, Switch, TextField, Typography } from "@mui/material";
import { BaselineSeries, CandlestickSeries, ColorType, LineSeries, createChart, createSeriesMarkers, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { BacktestChartCandle, BacktestTrade, ElliottPattern } from "../../lib/backtest/types";

const chartTime = (timestamp: number) => Math.floor(timestamp/1000) as UTCTimestamp;

export function BacktestPriceChart({ candles, candlesByTimeframe, elliottPatterns, trades, elliottConfig }: {
  candles: BacktestChartCandle[];
  candlesByTimeframe: Record<string, BacktestChartCandle[]>;
  trades: BacktestTrade[];
  elliottPatterns: ElliottPattern[];
  elliottConfig?: { wave2MinRetracement?: number; wave2MaxRetracement?: number; entryModel?: string };
}) {
  const available = Object.keys(candlesByTimeframe);
  const [timeframe, setTimeframe] = useState(available[0] ?? "PRIMARY");
  const [showTrades, setShowTrades] = useState(true);
  const [showWaves, setShowWaves] = useState(true);
  const [showInternalWaves, setShowInternalWaves] = useState(true);
  const [showRetracement, setShowRetracement] = useState(true);
  const [isRendering, setIsRendering] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fitRef = useRef<() => void>(() => undefined);
  const visibleRangeRef = useRef<ReturnType<IChartApi["timeScale"]>["getVisibleRange"] extends () => infer R ? R : never>(null);
  const selectedCandles = candlesByTimeframe[timeframe] ?? candles;
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
      wave.setData(points.map((point) => ({
        time: chartTime(nearestTimestamp(selectedCandles, point.confirmedAt)), value: point.price,
      })));
      if (showInternalWaves && (pattern.internalPoints?.length ?? 0) > 1) {
        const internal=activeChart.addSeries(LineSeries,{
          color:pattern.direction === "LONG" ? "#90caf9" : "#ce93d8",lineWidth:1,lineStyle:2,
          priceLineVisible:false,lastValueVisible:false,title:`Внутренние · ${pattern.entryTimeframe}`,
        });
        const data=[...new Map((pattern.internalPoints ?? []).map((point) => {
          const time=chartTime(nearestTimestamp(selectedCandles,point.timestamp));
          return [Number(time),{ time,value:point.price }] as const;
        })).values()].sort((left,right) => Number(left.time)-Number(right.time));
        if (data.length > 1) internal.setData(data);
      }
      if (showRetracement) {
        const p0=pattern.points.P0;const p1=pattern.points.P1;const p2=pattern.points.P2;
        if (p0 && p1 && p2) {
          const from=nearestTimestamp(selectedCandles,p1.timestamp);
          const to=nearestTimestamp(selectedCandles,p2.confirmedAt);
          const min=elliottConfig?.wave2MinRetracement;
          const max=elliottConfig?.wave2MaxRetracement;
          if (min != null) addBacktestLevel(activeChart,from,to,p1.price-(p1.price-p0.price)*min,"#7e57c2",`W2 min ${(min*100).toFixed(1)}%`);
          if (max != null) addBacktestLevel(activeChart,from,to,p1.price-(p1.price-p0.price)*max,"#7e57c2",`W2 max ${(max*100).toFixed(1)}%`);
          const actual=typeof pattern.features.wave2_retracement === "number" ? pattern.features.wave2_retracement
            : Math.abs(p2.price-p1.price)/Math.max(Math.abs(p1.price-p0.price),1e-12);
          addBacktestLevel(activeChart,from,to,p2.price,"#b39ddb",`W2 факт ${(actual*100).toFixed(1)}%`,2);
        }
      }
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
        text: `${trade.direction} #${trade.id} · ${elliottConfig?.entryModel ?? trade.signalTimeframe ?? "—"}` },
      { time: chartTime(trade.exitTime), position: "inBar" as const, color: trade.pnl >= 0 ? "#ffd54f" : "#ff9800",
        shape: "circle" as const, text: `Exit ${trade.pnl.toFixed(2)}` },
    ]) : [];
    const waveMarkers = showWaves ? elliottPatterns.filter((pattern) => pattern.state !== "INVALID").flatMap((pattern) =>
      Object.entries(pattern.points).map(([label, point]) => ({
        time: chartTime(nearestTimestamp(selectedCandles, point.confirmedAt)),
        position: point.kind === "LOW" ? "belowBar" as const : "aboveBar" as const,
        color: pattern.direction === "LONG" ? "#42a5f5" : "#ab47bc", shape: "circle" as const,
        text: `${label} подтвержд. · ${pattern.structureTimeframe}`,
      }))) : [];
    const markers = [...tradeMarkers, ...waveMarkers].sort((left,right) => Number(left.time)-Number(right.time));
    createSeriesMarkers(candleSeries, markers);
    if (visibleRangeRef.current) activeChart.timeScale().setVisibleRange(visibleRangeRef.current);
    else activeChart.timeScale().fitContent();
    activeChart.timeScale().subscribeVisibleTimeRangeChange((range) => { if (range) visibleRangeRef.current = range; });
    fitRef.current = () => activeChart.timeScale().fitContent();
    observer = new ResizeObserver(() => chart?.applyOptions({ width: container.clientWidth }));
    observer.observe(container);
    setIsRendering(false);
    fitRef.current();
    });
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      chart?.remove();
    };
  }, [elliottConfig, elliottPatterns, selectedCandles, showInternalWaves, showRetracement, showTrades, showWaves, trades]);

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
          onChange={(event) => { visibleRangeRef.current = null; setIsRendering(true); setTimeframe(event.target.value); }} sx={{ minWidth: 125 }}>
          {available.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>}
        <Button variant="outlined" onClick={() => fitRef.current()}>Весь период</Button>
        <Button variant="contained" onClick={() => void toggleFullscreen()}>
          {isFullscreen ? "Выйти из полного экрана" : "На весь экран"}
        </Button>
      </Stack>
    </Stack>
    <Paper variant="outlined" sx={{ mb: 1.5, p: 1.25, bgcolor: "action.hover" }}>
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", gap: 1 }}>
      </Stack>
      <Stack direction="row" useFlexGap sx={{ alignItems: "center", flexWrap: "wrap", gap: .5, mt: 1 }}>
        <FormControlLabel control={<Switch size="small" checked={showTrades} onChange={(_,value) => setShowTrades(value)} />} label="Сделки" />
        <FormControlLabel control={<Switch size="small" checked={showWaves} onChange={(_,value) => setShowWaves(value)} />} label="Волны Elliott" />
        <FormControlLabel control={<Switch size="small" checked={showInternalWaves} onChange={(_,value) => setShowInternalWaves(value)} />} label="Внутренние" />
        <FormControlLabel control={<Switch size="small" checked={showRetracement} onChange={(_,value) => setShowRetracement(value)} />} label="Retracement W2" />
      </Stack>
    </Paper>
    <Stack direction="row" spacing={.75} sx={{ mb: 1 }}><Chip size="small" color="success" label="Long" />
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

function addBacktestLevel(chart:IChartApi,from:number,to:number,value:number,color:string,label:string,lineWidth:1|2=1) {
  if (!Number.isFinite(value) || from >= to) return;
  const series=chart.addSeries(LineSeries,{ color,lineWidth,lineStyle:3,priceLineVisible:false,lastValueVisible:false,title:label });
  series.setData([{ time:chartTime(from),value },{ time:chartTime(to),value }]);
}
