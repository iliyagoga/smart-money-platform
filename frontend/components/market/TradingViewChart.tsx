"use client";

import { Box, Button, Chip, CircularProgress, FormControlLabel, Paper, Stack, Switch, TablePagination, Typography } from "@mui/material";
import { BaselineSeries, CandlestickSeries, ColorType, LineSeries, createChart, createSeriesMarkers, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePagination } from "../../hooks/usePagination";
import type { Candle } from "../../lib/types";

export interface LiveElliottPoint { timestamp: number; confirmed_at: number; price: number; kind: "HIGH" | "LOW" }
export interface LiveElliottPattern {
  id: string; direction: "LONG" | "SHORT"; state: string; invalid_reason?: string; signal_time?: number;
  structure_timeframe: string; entry_timeframe: string; points: Record<string, LiveElliottPoint>;
  features?: Record<string, number | string>;
  internal_points?: LiveElliottPoint[];
  strategy_levels?: {
    wave1_break: number; wave2_zone_low: number; wave2_zone_high: number;
    wave2_min_retracement: number; wave2_max_retracement: number;
    structure_from: number; structure_to: number; choch?: number; choch_close?: number;
    entry?: number; stop?: number; targets?: number[]; trade_from?: number; trade_to?: number;
  };
}
export interface LiveEntryScenario {
  id: string; direction: "LONG" | "SHORT"; setup_type: string; status: string;
  trade_id?: string;
  entry_type?: "LIMIT" | "MARKET" | "STOP"; entry_zone_low: number; entry_zone_high: number;
  created_at: number; expires_at: number;
  entry_model?: string;
  origin?: "HISTORICAL" | "LIVE";
  stop_loss_price?: number;
  take_profit_prices?: number[];
}
export interface HistoricalPaperTrade {
  id: string; direction: "LONG" | "SHORT"; entry_time: number; entry_price: number;
  exit_time: number; exit_price: number; pnl: number; pnl_percent: number; reason: string;
  initial_stop?: number; take_profit_prices?: number[]; signal_timeframe?: string;
}

type ChartSeries = ReturnType<ReturnType<typeof createChart>["addSeries"]>;

export function TradingViewChart({ candles, elliottPatterns = [], entryScenarios = [], historicalTrades = [], isLoading = false }: {
  candles: Candle[]; elliottPatterns?: LiveElliottPattern[]; entryScenarios?: LiveEntryScenario[];
  historicalTrades?: HistoricalPaperTrade[]; isLoading?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>["addSeries"]> | null>(null);
  const waveSeriesRef = useRef<ChartSeries[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const overlayFingerprintRef = useRef("");
  const renderedCandlesRef = useRef<Candle[]>([]);
  const pendingFocusRef = useRef<{ from:UTCTimestamp;to:UTCTimestamp } | null>(null);
  const hasInitialFitRef = useRef(false);
  const [selectedEntryId,setSelectedEntryId] = useState("");
  const [isFullscreen,setIsFullscreen] = useState(false);
  const [windowCenter,setWindowCenter] = useState<number | null>(null);
  const [showWaves,setShowWaves] = useState(true);
  const [showInternalWaves,setShowInternalWaves] = useState(true);
  const [showRetracement,setShowRetracement] = useState(true);
  const [showEntries,setShowEntries] = useState(true);
  const [showRiskLevels,setShowRiskLevels] = useState(true);
  const chartCandles = useMemo(() => candleWindow(candles,windowCenter,10_000),[candles,windowCenter]);
  useEffect(() => {
    const container = ref.current; if (!container) return;
    const chart = createChart(container, { width: container.clientWidth, height: container.clientHeight || 560,
      layout: { background: { type: ColorType.Solid, color: "#101722" }, textColor: "#b2b9c6", attributionLogo: true },
      grid: { vertLines: { color: "#1e2938" }, horzLines: { color: "#1e2938" } },
      rightPriceScale: { borderColor: "#334155", autoScale: true, scaleMargins: { top: .12, bottom: .12 } }, timeScale: {
        borderColor: "#334155", timeVisible: true,
        tickMarkFormatter: (time: number) => formatDubaiTime(time),
      },
      localization: { timeFormatter: (time: number) => formatDubaiTime(time) },
      handleScroll: { mouseWheel: true, pressedMouseMove: true }, handleScale: { mouseWheel: true, pinch: true },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#26a69a", downColor: "#ef5350", wickUpColor: "#26a69a", wickDownColor: "#ef5350", borderVisible: false,
    });
    chartRef.current = chart; seriesRef.current = series;
    const resize = () => chart.applyOptions({ width: container.clientWidth, height: container.clientHeight || 560 });
    const observer = new ResizeObserver(resize); observer.observe(container);
    return () => { observer.disconnect(); chart.remove(); };
  }, []);
  useEffect(() => {
    const update = () => setIsFullscreen(document.fullscreenElement === fullscreenRef.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);
  const toggleFullscreen = async () => {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await fullscreenRef.current?.requestFullscreen();
  };
  const autoFit = () => {
    chartRef.current?.priceScale("right").applyOptions({ autoScale: true });
    chartRef.current?.timeScale().fitContent();
  };
  useEffect(() => {
    const series = seriesRef.current; const chart = chartRef.current;
    if (!series || !chart || !chartCandles.length) return;
    const previous=renderedCandlesRef.current;const last=chartCandles.at(-1)!;
    const latestOnly=previous.length === chartCandles.length && previous.length > 0
      && previous[0].timestamp === chartCandles[0].timestamp
      && previous.at(-2)?.timestamp === chartCandles.at(-2)?.timestamp;
    if (latestOnly) series.update({ time:chartTime(last.timestamp),open:last.open,high:last.high,low:last.low,close:last.close });
    else series.setData(chartCandles.map((c) => ({
      time: chartTime(c.timestamp), open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    renderedCandlesRef.current=chartCandles;
    if (pendingFocusRef.current) {
      chart.timeScale().setVisibleRange(pendingFocusRef.current);
      pendingFocusRef.current=null;
    }
  }, [chartCandles]);
  useEffect(() => {
    const chart = chartRef.current; const candleSeries = seriesRef.current;
    if (!chart || !candleSeries || !chartCandles.length) return;
    const orderedCandles = chartCandles;
    const visibleFrom=orderedCandles[0].timestamp;const visibleTo=orderedCandles.at(-1)?.timestamp ?? visibleFrom;
    const visiblePatterns=elliottPatterns.filter((pattern) => pattern.state !== "INVALID" && patternOverlaps(pattern,visibleFrom,visibleTo));
    const visibleEntries=entryScenarios.filter((scenario) => scenario.setup_type === "ELLIOTT_WAVE3"
      && scenario.expires_at >= visibleFrom && scenario.created_at <= visibleTo);
    const visibleTrades=historicalTrades.filter((trade) => trade.exit_time >= visibleFrom && trade.entry_time <= visibleTo
      && !(trade.reason === "END_OF_DATA" && trade.exit_time < visibleTo));
    const overlayFingerprint=[visibleFrom,visibleTo,selectedEntryId,showWaves,showInternalWaves,showRetracement,showEntries,showRiskLevels,
      ...visiblePatterns.map((item) => `${item.id}:${item.state}:${item.direction}:${item.structure_timeframe}:${Object.values(item.points).map((point) => `${point.timestamp}:${point.price}`).join(",")}:${JSON.stringify(item.strategy_levels ?? null)}`),
      ...visiblePatterns.flatMap((item) => (item.internal_points ?? []).map((point) => `${point.timestamp}:${point.price}`)),
      ...visibleEntries.map((item) => `${item.id}:${item.status}:${item.entry_model ?? item.entry_type ?? ""}:${item.stop_loss_price ?? ""}:${item.take_profit_prices?.join(",") ?? ""}:${entryResult(item,orderedCandles)}`),
      ...visibleTrades.map((item) => `${item.id}:${item.pnl}:${item.initial_stop ?? ""}:${item.take_profit_prices?.join(",") ?? ""}`)].join("|");
    if (overlayFingerprintRef.current === overlayFingerprint) return;
    overlayFingerprintRef.current=overlayFingerprint;
    const staleSeries = waveSeriesRef.current;
    waveSeriesRef.current = [];
    staleSeries.forEach((series) => chart.removeSeries(series));
    const markers: SeriesMarker<Time>[] = [];
    visiblePatterns.forEach((pattern) => {
      const points = ["P0", "P1", "P2", "P3", "P4", "P5", "A", "B", "C"]
        .flatMap((label) => pattern.points[label] ? [{ label, ...pattern.points[label] }] : []);
      if (points.length < 2) return;
      const color = pattern.direction === "LONG" ? "#42a5f5" : "#ce93d8";
      const waveData = [...new Map(points.map((point) => {
        const time = chartTime(containingCandleTimestamp(orderedCandles, point.timestamp));
        return [Number(time), { time, value: point.price }] as const;
      })).values()].sort((left, right) => Number(left.time) - Number(right.time));
      // Several lower-timeframe pivots can map to one H4/D1 candle. The chart
      // requires strictly increasing timestamps, so collapsed waves are skipped.
      if (waveData.length < 2) return;
      if (showWaves) {
        const wave = chart.addSeries(LineSeries, { color, lineWidth: 3, priceLineVisible: false,
          lastValueVisible: false, title: "" });
        wave.setData(waveData);
        waveSeriesRef.current.push(wave);
        const waveMarkers = [...new Map(points.map((point) => {
          const time = chartTime(containingCandleTimestamp(orderedCandles, point.timestamp));
          return [Number(time), { time, position: point.kind === "LOW" ? "belowBar" as const : "aboveBar" as const,
            color, shape: "circle" as const,
            text: `${point.label}${waveLegend(point.label) ? ` · ${waveLegend(point.label)}` : ""} · ${pattern.structure_timeframe}` }] as const;
        })).values()].sort((left, right) => Number(left.time) - Number(right.time));
        createSeriesMarkers(wave, waveMarkers, { autoScale: false });
      }
      if (showInternalWaves) addInternalWave(chart,waveSeriesRef.current,orderedCandles,pattern,color);
      if (showRetracement) addRetracement(chart,waveSeriesRef.current,orderedCandles,pattern);
      const levels = pattern.strategy_levels;
      if (levels && showWaves) {
        const structureFrom = containingCandleTimestamp(orderedCandles, levels.structure_from);
        const structureTo = containingCandleTimestamp(orderedCandles, levels.structure_to);
        addLevel(chart, waveSeriesRef.current, structureFrom, structureTo, levels.wave1_break,
          "#90caf9", "Пробой Wave 1", 2);
        if (levels.choch != null && levels.trade_from != null) {
          addLevel(chart, waveSeriesRef.current, structureTo,
            containingCandleTimestamp(orderedCandles, levels.trade_from), levels.choch,
            "#ffb74d", "CHOCH", 2);
        }
      }
    });
    const historicalTradeIds = new Set(visibleTrades.map((trade) => trade.id));
    if (showEntries) visibleEntries.forEach((scenario) => {
      const start = nearestTimestamp(orderedCandles,scenario.created_at);
      const linkedTrade=visibleTrades.find((trade) => trade.id === (scenario.trade_id ?? scenario.id));
      const rawEnd=linkedTrade?.exit_time ?? Math.min(scenario.expires_at,orderedCandles.at(-1)?.timestamp ?? scenario.expires_at);
      const end = levelEndTimestamp(orderedCandles,start,nearestTimestamp(orderedCandles,rawEnd));
      const entry = (scenario.entry_zone_low+scenario.entry_zone_high)/2;
      const result = entryResult(scenario,orderedCandles);
      const color = scenario.origin === "LIVE"
        ? (result === "PASSED" ? "#00e676" : result === "WAITING" ? "#ffca28" : "#90a4ae")
        : (result === "PASSED" ? "#2e7d32" : result === "WAITING" ? "#9e7d24" : "#546e7a");
      addLevel(chart,waveSeriesRef.current,start,end,entry,color,
        `ENTRY · ${entryModelLabel(scenario.entry_model)} · ${scenario.entry_type ?? "—"}`,
        result === "MISSED" ? 3 : 2,scenario.id === selectedEntryId ? 4 : 2);
      if (Math.abs(scenario.entry_zone_high-scenario.entry_zone_low) > 1e-12) {
        addLevel(chart,waveSeriesRef.current,start,end,scenario.entry_zone_low,color,"Entry zone low",3);
        addLevel(chart,waveSeriesRef.current,start,end,scenario.entry_zone_high,color,"Entry zone high",3);
      }
      if (showRiskLevels && scenario.stop_loss_price != null) {
        addLevel(chart,waveSeriesRef.current,start,end,scenario.stop_loss_price,"#ef5350","SL",2,2);
        (scenario.take_profit_prices ?? []).forEach((target,index) =>
          addLevel(chart,waveSeriesRef.current,start,end,target,"#26a69a",`TP${index+1}`,2,2));
      }
      if (!historicalTradeIds.has(scenario.trade_id ?? scenario.id)) {
        markers.push({ time: chartTime(start), position: scenario.direction === "LONG" ? "belowBar" : "aboveBar",
          color, shape: scenario.direction === "LONG" ? "arrowUp" : "arrowDown",
          text: `Вход · ${scenario.origin === "LIVE" ? "LIVE" : "История"} · ${entryResultLabel(result)} · ${scenario.direction} · Модель: ${scenario.entry_model ?? scenario.entry_type ?? "—"}` });
      }
    });
    visibleTrades.forEach((trade) => {
      const entryTime=nearestTimestamp(orderedCandles,trade.entry_time);
      const exitTime=nearestTimestamp(orderedCandles,trade.exit_time);
      if (entryTime !== exitTime) {
        const tradeLine=chart.addSeries(LineSeries,{ color:trade.pnl >= 0 ? "#26a69a" : "#ef5350",lineWidth:2,
          lineStyle:2,priceLineVisible:false,lastValueVisible:false,title:"" });
        tradeLine.setData([
          { time:chartTime(entryTime),value:trade.entry_price },
          { time:chartTime(exitTime),value:trade.exit_price },
        ]);
        waveSeriesRef.current.push(tradeLine);
      }
      const hasScenarioLevels=visibleEntries.some((scenario) => (scenario.trade_id ?? scenario.id) === trade.id);
      if (showRiskLevels && !hasScenarioLevels) {
        const riskEnd=levelEndTimestamp(orderedCandles,entryTime,exitTime);
        if (trade.initial_stop != null) addLevel(chart,waveSeriesRef.current,entryTime,riskEnd,
          trade.initial_stop,"#ef5350","SL · сделка",2,2);
        (trade.take_profit_prices ?? []).forEach((target,index) => addLevel(chart,waveSeriesRef.current,
          entryTime,riskEnd,target,"#26a69a",`TP${index+1} · сделка`,2,2));
      }
      markers.push({ time:chartTime(entryTime),position:trade.direction === "LONG" ? "belowBar" : "aboveBar",
        color:trade.direction === "LONG" ? "#2e7d32" : "#c62828",
        shape:trade.direction === "LONG" ? "arrowUp" : "arrowDown",
        text:`Сделка · вход · ${trade.direction} · ${trade.entry_price}` });
      markers.push({ time:chartTime(nearestTimestamp(orderedCandles,trade.exit_time)),
        position:trade.pnl >= 0 ? "aboveBar" : "belowBar",color:trade.pnl >= 0 ? "#26a69a" : "#ef5350",
        shape:"square",text:`Выход · ${trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)} · ${trade.reason}` });
    });
    const sortedMarkers = markers.sort((left, right) => Number(left.time) - Number(right.time));
    if (!markersRef.current) markersRef.current = createSeriesMarkers(candleSeries, sortedMarkers, { autoScale: false });
    else markersRef.current.setMarkers(sortedMarkers);
  }, [chartCandles, elliottPatterns, entryScenarios, historicalTrades, selectedEntryId,
    showEntries,showInternalWaves,showRetracement,showRiskLevels,showWaves]);
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !chartCandles.length || isLoading || hasInitialFitRef.current) return;
    hasInitialFitRef.current = true;
    // Data and overlays are installed by the effects above. Waiting for the next
    // frame makes the first autoscale deterministic even when candles came from
    // IndexedDB first and were then extended with paginated history.
    const frame = window.requestAnimationFrame(() => {
      chart.priceScale("right").applyOptions({ autoScale: true });
      chart.timeScale().fitContent();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [chartCandles, elliottPatterns, entryScenarios, historicalTrades, isLoading]);
  const validPatterns = elliottPatterns.filter((pattern) => pattern.state !== "INVALID").length;
  const entries = entryScenarios.filter((scenario) => scenario.setup_type === "ELLIOTT_WAVE3")
    .sort((left,right) => right.created_at-left.created_at);
  const entryPagination=usePagination(entries,10);
  return <Paper ref={fullscreenRef} variant="outlined" sx={{ p: 1, overflow: "hidden", position: "relative",
    "&:fullscreen": { bgcolor: "#101722", width: "100vw", height: "100vh", display: "flex", flexDirection: "column", p: 1 } }}>
    <Stack direction="row" sx={{ px: 1, pb: 1, gap: 1, justifyContent: "space-between", alignItems: "center" }}>
      <Typography variant="subtitle2">График актива</Typography>
      <Stack direction="row" sx={{ gap: 1, alignItems: "center" }}>
        <Typography variant="caption" color={validPatterns ? "primary.light" : "text.secondary"}>Elliott: {validPatterns} волн · потенциальных входов: {entries.length}</Typography>
        <Button size="small" variant="outlined" onClick={() => void toggleFullscreen()} sx={{ minWidth: 112, py: .35, textTransform: "none" }}>
          {isFullscreen ? "Свернуть" : "На весь экран"}
        </Button>
      </Stack>
    </Stack>
    <Stack direction="row" useFlexGap sx={{ px:1,pb:1,gap:.25,alignItems:"center",flexWrap:"wrap" }}>
      <FormControlLabel control={<Switch size="small" checked={showWaves} onChange={(_,value) => setShowWaves(value)} />} label="Волны" />
      <FormControlLabel control={<Switch size="small" checked={showInternalWaves} onChange={(_,value) => setShowInternalWaves(value)} />} label="Внутренние" />
      <FormControlLabel control={<Switch size="small" checked={showRetracement} onChange={(_,value) => setShowRetracement(value)} />} label="Retracement W2" />
      <FormControlLabel control={<Switch size="small" checked={showEntries} onChange={(_,value) => setShowEntries(value)} />} label="Входы" />
      <FormControlLabel control={<Switch size="small" checked={showRiskLevels} onChange={(_,value) => setShowRiskLevels(value)} />} label="SL / TP" />
      <Stack direction="row" useFlexGap sx={{ ml:{ sm:"auto" },gap:.5,flexWrap:"wrap" }}>
        <Chip size="small" sx={{ color:"#42a5f5",borderColor:"#42a5f5" }} variant="outlined" label="Elliott" />
        <Chip size="small" sx={{ color:"#ffb74d",borderColor:"#ffb74d" }} variant="outlined" label="Entry" />
        <Chip size="small" color="error" variant="outlined" label="SL" />
        <Chip size="small" color="success" variant="outlined" label="TP" />
      </Stack>
    </Stack>
    <Box sx={{ position: "relative", width: "100%", height: isFullscreen ? "calc(100vh - 54px)" : 560, flex: isFullscreen ? 1 : "none" }}>
      <Box ref={ref} sx={{ width: "100%", height: "100%" }} />
      {isLoading && <Stack role="status" aria-live="polite" direction="row" spacing={1}
        sx={{ position:"absolute",top:10,left:10,zIndex:4,alignItems:"center",px:1.25,py:.75,
          borderRadius:1,bgcolor:"rgba(16,23,34,.9)",color:"#dbe5f1",boxShadow:"0 2px 8px rgba(0,0,0,.3)" }}>
        <CircularProgress size={16} color="inherit"/><Typography variant="caption">Загрузка данных графика…</Typography>
      </Stack>}
      {!isLoading && !candles.length && <Stack sx={{ position:"absolute",inset:0,alignItems:"center",justifyContent:"center",
        color:"#b2b9c6",pointerEvents:"none" }}><Typography>Для выбранного периода свечей нет.</Typography></Stack>}
      <Button aria-label="Автовыравнивание графика" title="Автовыравнивание" onClick={autoFit}
        variant="contained" size="small" sx={{ position: "absolute", right: 10, bottom: 28, zIndex: 3,
          minWidth: 32, width: 32, height: 28, p: 0, bgcolor: "rgba(38,50,66,.92)", color: "#dbe5f1",
          border: "1px solid #526174", boxShadow: "none", "&:hover": { bgcolor: "#334155", boxShadow: "none" } }}>A</Button>
    </Box>
    {!isFullscreen && <Paper variant="outlined" sx={{ mt: 1, p: 1.5, bgcolor: "rgba(255,255,255,.02)" }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Потенциальные точки входа выбранного актива</Typography>
      {entries.length ? <><Stack spacing={.75}>{entryPagination.visible.map((scenario) => {
        const result = entryResult(scenario,candles); const entry = (scenario.entry_zone_low+scenario.entry_zone_high)/2;
        const focus = () => {
          setSelectedEntryId(scenario.id);
          const duration = Math.max(60_000,scenario.expires_at-scenario.created_at);
          const range={
            from: chartTime(scenario.created_at-duration*.5),
            to: chartTime(scenario.expires_at+duration*.5),
          };
          const first=chartCandles[0]?.timestamp;const last=chartCandles.at(-1)?.timestamp;
          if (first != null && last != null && scenario.created_at >= first && scenario.created_at <= last) {
            chartRef.current?.timeScale().setVisibleRange(range);
          } else {
            pendingFocusRef.current=range;setWindowCenter(scenario.created_at);
          }
        };
        return <Stack key={scenario.id} direction={{ xs: "column", sm: "row" }} role="button" tabIndex={0}
          onClick={focus} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") focus(); }}
          sx={{ gap: 1, alignItems: { sm: "center" }, py: .75, px: 1, borderBottom: 1,
            borderColor: selectedEntryId === scenario.id ? "primary.main" : "divider", borderRadius: 1,
            cursor: "pointer", bgcolor: selectedEntryId === scenario.id ? "action.selected" : "transparent",
            "&:hover": { bgcolor: "action.hover" }, "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main" } }}>
          <Chip size="small" color={result === "PASSED" ? "success" : result === "WAITING" ? "warning" : "default"} label={entryResultLabel(result)} sx={{ minWidth: 145 }} />
          <Chip size="small" variant={scenario.origin === "LIVE" ? "filled" : "outlined"}
            color={scenario.origin === "LIVE" ? "info" : "default"}
            label={scenario.origin === "LIVE" ? "LIVE" : "История"} sx={{ minWidth: 82 }} />
          <Typography variant="body2" color={scenario.direction === "LONG" ? "success.light" : "error.light"} sx={{ minWidth: 55, fontWeight: 700 }}>{scenario.direction}</Typography>
          <Typography variant="body2" sx={{ minWidth: 110 }}>Вход: {entry.toLocaleString("ru-RU",{ maximumFractionDigits: 8 })}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 145 }}>{scenario.entry_model ?? scenario.entry_type ?? "—"}</Typography>
          <Typography variant="caption" color="text.secondary">Сигнал: {formatDubaiTimestamp(scenario.created_at)} · до {formatDubaiTimestamp(scenario.expires_at)}</Typography>
        </Stack>;
      })}</Stack><TablePagination component="div" {...entryPagination.paginationProps} /></>
        : <Typography variant="body2" color="text.secondary">Потенциальных входов пока нет.</Typography>}
    </Paper>}
    {!isFullscreen && historicalTrades.length > 0 && <Paper variant="outlined" sx={{ mt:1,p:1.5,bgcolor:"rgba(255,255,255,.02)" }}>
      <Typography variant="subtitle2" sx={{ mb:1 }}>Исторические paper-сделки · не входят в общий PnL</Typography>
      <Stack spacing={.5}>{[...historicalTrades].sort((left,right) => right.entry_time-left.entry_time).slice(0,20).map((trade) => {
        const focus = () => {
          const padding=Math.max(60_000,(trade.exit_time-trade.entry_time)*.25);
          const range={ from:chartTime(trade.entry_time-padding),to:chartTime(trade.exit_time+padding) };
          const first=chartCandles[0]?.timestamp;const last=chartCandles.at(-1)?.timestamp;
          if (first != null && last != null && trade.entry_time >= first && trade.exit_time <= last) {
            chartRef.current?.timeScale().setVisibleRange(range);
          } else {
            pendingFocusRef.current=range;setWindowCenter(trade.entry_time);
          }
        };
        return <Stack key={trade.id} direction={{ xs:"column",sm:"row" }} role="button" tabIndex={0}
          onClick={focus} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") focus(); }}
          sx={{ gap:1,py:.6,px:.5,borderBottom:1,borderColor:"divider",borderRadius:1,cursor:"pointer",
            "&:hover":{ bgcolor:"action.hover" },"&:focus-visible":{ outline:"2px solid",outlineColor:"primary.main" } }}>
          <Typography variant="body2" color={trade.direction === "LONG" ? "success.light" : "error.light"} sx={{ minWidth:55,fontWeight:700 }}>{trade.direction}</Typography>
          <Typography variant="caption" sx={{ minWidth:170 }}>{formatDubaiTimestamp(trade.entry_time)} → {formatDubaiTimestamp(trade.exit_time)}</Typography>
          <Typography variant="caption" sx={{ minWidth:180 }}>Вход {trade.entry_price.toLocaleString("ru-RU")} · выход {trade.exit_price.toLocaleString("ru-RU")}</Typography>
          <Typography variant="body2" color={trade.pnl >= 0 ? "success.main" : "error.main"} sx={{ fontWeight:700 }}>{trade.pnl >= 0 ? "+" : ""}{trade.pnl.toFixed(2)} ({trade.pnl_percent.toFixed(2)}%)</Typography>
        </Stack>;
      })}</Stack>
    </Paper>}
  </Paper>;
}

type EntryResult = "PASSED" | "WAITING" | "MISSED";

function entryResult(scenario: LiveEntryScenario,candles: Candle[]): EntryResult {
  if (scenario.entry_type === "MARKET") return "PASSED";
  const entry = (scenario.entry_zone_low+scenario.entry_zone_high)/2;
  const touched = candles.some((candle) => candle.timestamp >= scenario.created_at
    && candle.timestamp <= scenario.expires_at && candle.low <= entry && candle.high >= entry);
  if (touched) return "PASSED";
  return scenario.expires_at >= Date.now() ? "WAITING" : "MISSED";
}

function entryResultLabel(result: EntryResult) {
  return result === "PASSED" ? "Уровень достигнут" : result === "WAITING" ? "Ожидает входа" : "Не сработал";
}

const chartTime = (timestamp: number) => Math.floor(timestamp / 1000) as UTCTimestamp;

function addLevel(chart: ReturnType<typeof createChart>, collection: ChartSeries[],
  from: number, to: number, value: number, color: string, label: string, lineStyle: number,
  lineWidth: 1 | 2 | 3 | 4 = 1) {
  if (!Number.isFinite(value) || from >= to) return;
  const series = chart.addSeries(LineSeries, { color, lineWidth, lineStyle,
    priceLineVisible: false, lastValueVisible: false, title: "" });
  const startTime = chartTime(from); const endTime = chartTime(to);
  series.setData([{ time: startTime, value }, { time: endTime, value }]);
  createSeriesMarkers(series, [{ time: endTime, position: "aboveBar", color, shape: "circle", text: label }],
    { autoScale: false });
  collection.push(series);
}

function addRetracement(chart:ReturnType<typeof createChart>,collection:ChartSeries[],candles:Candle[],pattern:LiveElliottPattern) {
  const p0=pattern.points.P0;const p1=pattern.points.P1;const p2=pattern.points.P2;
  if (!p0 || !p1 || !p2) return;
  const from=containingCandleTimestamp(candles,p1.timestamp);
  const to=levelEndTimestamp(candles,from,containingCandleTimestamp(candles,
    pattern.strategy_levels?.trade_to ?? pattern.signal_time ?? p2.confirmed_at));
  const levels=pattern.strategy_levels;
  if (levels) {
    const zone=chart.addSeries(BaselineSeries,{
      baseValue:{ type:"price",price:levels.wave2_zone_low },lineVisible:false,
      topFillColor1:"rgba(126,87,194,.18)",topFillColor2:"rgba(126,87,194,.06)",
      bottomFillColor1:"rgba(126,87,194,0)",bottomFillColor2:"rgba(126,87,194,0)",
      priceLineVisible:false,lastValueVisible:false,title:"",
    });
    zone.setData([{ time:chartTime(from),value:levels.wave2_zone_high },
      { time:chartTime(to),value:levels.wave2_zone_high }]);
    collection.push(zone);
    addLevel(chart,collection,from,to,levels.wave2_zone_high,"#7e57c2",
      `W2 min ${(levels.wave2_min_retracement*100).toFixed(1)}%`,3);
    addLevel(chart,collection,from,to,levels.wave2_zone_low,"#7e57c2",
      `W2 max ${(levels.wave2_max_retracement*100).toFixed(1)}%`,3);
  }
  const retracement=typeof pattern.features?.wave2_retracement === "number"
    ? pattern.features.wave2_retracement : Math.abs(p2.price-p1.price)/Math.max(Math.abs(p1.price-p0.price),1e-12);
  addLevel(chart,collection,from,to,p2.price,"#b39ddb",`W2 факт ${(retracement*100).toFixed(1)}%`,2,2);
}

function addInternalWave(chart:ReturnType<typeof createChart>,collection:ChartSeries[],candles:Candle[],
  pattern:LiveElliottPattern,color:string) {
  const points=pattern.internal_points ?? [];
  const data=[...new Map(points.map((point) => {
    const time=chartTime(containingCandleTimestamp(candles,point.timestamp));
    return [Number(time),{ time,value:point.price,kind:point.kind }] as const;
  })).values()].sort((left,right) => Number(left.time)-Number(right.time));
  if (data.length < 2) return;
  const series=chart.addSeries(LineSeries,{ color,lineWidth:1,lineStyle:2,priceLineVisible:false,
    lastValueVisible:false,title:"" });
  series.setData(data.map(({ time,value }) => ({ time,value })));
  createSeriesMarkers(series,data.map((point,index) => ({ time:point.time,
    position:point.kind === "LOW" ? "belowBar" as const : "aboveBar" as const,
    color,shape:"circle" as const,text:`μ${index+1} · ${pattern.entry_timeframe}` })),{ autoScale:false });
  collection.push(series);
}

function levelEndTimestamp(candles:Candle[],start:number,end:number) {
  if (end > start) return end;
  const index=candles.findIndex((item) => item.timestamp === start);
  return candles[index+1]?.timestamp ?? start+60_000;
}

function entryModelLabel(model?:string) {
  return ({
    CHOCH_MARKET:"CHOCH по рынку",CHOCH_RETRACE:"CHOCH ретест",WAVE1_BREAK_RETRACE:"Пробой W1 + ретест",
    WAVE1_BREAK_MARKET:"Пробой W1",WAVE1_BREAK_STOP:"Стоп за W1",WAVE1_BREAK_RETEST_CONFIRM:"Ретест W1",
    MICRO_WAVE3:"Micro Wave 3",DISPLACEMENT_RETRACE:"Импульс + ретест",P2_LIQUIDITY_SWEEP:"Снятие P2",
    WAVE2_TRENDLINE_BREAK:"Пробой трендовой W2",ADX_ACCELERATION:"Ускорение ADX",
    VOLATILITY_EXPANSION:"Рост волатильности",VOLUME_EXPANSION:"Рост объёма",SIMULATION:"Симуляция",
  } as Record<string,string>)[model ?? ""] ?? model ?? "Модель входа";
}

function waveLegend(label: string) {
  return ({ P0: "Старт Wave 1", P1: "Wave 1", P2: "Wave 2", P3: "Wave 3",
    P4: "Wave 4", P5: "Wave 5", A: "Коррекция A", B: "Коррекция B", C: "Коррекция C" } as Record<string, string>)[label] ?? "";
}

function candleWindow(candles:Candle[],center:number|null,limit:number) {
  const ordered=[...candles].sort((left,right) => left.timestamp-right.timestamp);
  if (ordered.length <= limit) return ordered;
  if (center == null) return ordered.slice(-limit);
  let index=ordered.findIndex((item) => item.timestamp >= center);
  if (index < 0) index=ordered.length-1;
  const start=Math.max(0,Math.min(ordered.length-limit,index-Math.floor(limit/2)));
  return ordered.slice(start,start+limit);
}

function patternOverlaps(pattern:LiveElliottPattern,from:number,to:number) {
  const timestamps=Object.values(pattern.points).map((point) => point.timestamp);
  return Boolean(timestamps.length && Math.max(...timestamps) >= from && Math.min(...timestamps) <= to);
}

function nearestTimestamp(candles: Candle[], timestamp: number) {
  if (!candles.length) return timestamp;
  let left = 0; let right = candles.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (candles[middle].timestamp < timestamp) left = middle + 1;
    else right = middle;
  }
  return left > 0 && Math.abs(candles[left - 1].timestamp - timestamp) < Math.abs(candles[left].timestamp - timestamp)
    ? candles[left - 1].timestamp : candles[left].timestamp;
}

function containingCandleTimestamp(candles: Candle[], timestamp: number) {
  if (!candles.length) return timestamp;
  let left = 0; let right = candles.length - 1;
  while (left <= right) {
    const middle = Math.floor((left + right) / 2);
    if (candles[middle].timestamp <= timestamp) left = middle + 1;
    else right = middle - 1;
  }
  return candles[Math.max(0, right)].timestamp;
}

function formatDubaiTime(seconds: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Dubai", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
  }).format(new Date(seconds * 1000));
}

function formatDubaiTimestamp(timestamp: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Dubai", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
  }).format(new Date(timestamp));
}
