"use client";

import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import { CandlestickSeries, ColorType, LineSeries, createChart, createSeriesMarkers, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import type { Candle } from "../../lib/types";

export interface LiveElliottPoint { timestamp: number; confirmed_at: number; price: number; kind: "HIGH" | "LOW" }
export interface LiveElliottPattern {
  id: string; direction: "LONG" | "SHORT"; state: string; invalid_reason?: string; signal_time?: number;
  structure_timeframe: string; entry_timeframe: string; points: Record<string, LiveElliottPoint>;
}
export interface LiveEntryScenario {
  id: string; direction: "LONG" | "SHORT"; setup_type: string; status: string;
  entry_type?: "LIMIT" | "MARKET"; entry_zone_low: number; entry_zone_high: number;
  created_at: number; expires_at: number;
  entry_model?: string;
}

export function TradingViewChart({ candles, elliottPatterns = [], entryScenarios = [] }: {
  candles: Candle[]; elliottPatterns?: LiveElliottPattern[]; entryScenarios?: LiveEntryScenario[];
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>["addSeries"]> | null>(null);
  const waveSeriesRef = useRef<Array<ReturnType<ReturnType<typeof createChart>["addSeries"]>>>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const hasDataRef = useRef(false);
  const [selectedEntryId,setSelectedEntryId] = useState("");
  useEffect(() => {
    const container = ref.current; if (!container) return;
    const chart = createChart(container, { width: container.clientWidth, height: 560,
      layout: { background: { type: ColorType.Solid, color: "#101722" }, textColor: "#b2b9c6", attributionLogo: true },
      grid: { vertLines: { color: "#1e2938" }, horzLines: { color: "#1e2938" } },
      rightPriceScale: { borderColor: "#334155" }, timeScale: {
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
    const resize = () => chart.applyOptions({ width: container.clientWidth });
    const observer = new ResizeObserver(resize); observer.observe(container);
    return () => { observer.disconnect(); chart.remove(); };
  }, []);
  useEffect(() => {
    const series = seriesRef.current; const chart = chartRef.current;
    if (!series || !chart || !candles.length) return;
    series.setData([...candles].sort((a, b) => a.timestamp - b.timestamp).map((c) => ({
      time: Math.floor(c.timestamp / 1000) as UTCTimestamp, open: c.open, high: c.high, low: c.low, close: c.close,
    })));
    if (!hasDataRef.current) { chart.timeScale().fitContent(); hasDataRef.current = true; }
  }, [candles]);
  useEffect(() => {
    const chart = chartRef.current; const candleSeries = seriesRef.current;
    if (!chart || !candleSeries || !candles.length) return;
    waveSeriesRef.current.forEach((series) => chart.removeSeries(series));
    waveSeriesRef.current = [];
    const orderedCandles = [...candles].sort((a, b) => a.timestamp - b.timestamp);
    const markers: SeriesMarker<Time>[] = [];
    elliottPatterns.filter((pattern) => pattern.state !== "INVALID").forEach((pattern) => {
      const points = ["P0", "P1", "P2", "P3", "P4", "P5", "A", "B", "C"]
        .flatMap((label) => pattern.points[label] ? [{ label, ...pattern.points[label] }] : []);
      if (points.length < 2) return;
      const color = pattern.direction === "LONG" ? "#42a5f5" : "#ce93d8";
      const waveData = [...new Map(points.map((point) => {
        const time = chartTime(nearestTimestamp(orderedCandles, point.confirmed_at));
        return [Number(time), { time, value: point.price }] as const;
      })).values()].sort((left, right) => Number(left.time) - Number(right.time));
      // Several lower-timeframe pivots can map to one H4/D1 candle. The chart
      // requires strictly increasing timestamps, so collapsed waves are skipped.
      if (waveData.length < 2) return;
      const wave = chart.addSeries(LineSeries, { color, lineWidth: 3, priceLineVisible: false,
        lastValueVisible: false, title: "" });
      wave.setData(waveData);
      waveSeriesRef.current.push(wave);
      points.forEach((point) => markers.push({
        time: chartTime(nearestTimestamp(orderedCandles, point.confirmed_at)),
        position: point.kind === "LOW" ? "belowBar" : "aboveBar", color, shape: "circle",
        text: `${point.label} · ${pattern.structure_timeframe}`,
      }));
    });
    entryScenarios.filter((scenario) => scenario.setup_type === "ELLIOTT_WAVE3").forEach((scenario) => {
      const start = nearestTimestamp(orderedCandles,scenario.created_at);
      const end = nearestTimestamp(orderedCandles,Math.min(scenario.expires_at,orderedCandles.at(-1)?.timestamp ?? scenario.expires_at));
      if (start === end) return;
      const entry = (scenario.entry_zone_low+scenario.entry_zone_high)/2;
      const result = entryResult(scenario,orderedCandles);
      const color = result === "PASSED" ? "#00c853" : result === "WAITING" ? "#ffb300" : "#78909c";
      const line = chart.addSeries(LineSeries, { color, lineWidth: scenario.id === selectedEntryId ? 4 : 2,
        lineStyle: result === "MISSED" ? 3 : 2,
        priceLineVisible: false, lastValueVisible: false, title: "" });
      line.setData([{ time: chartTime(start), value: entry }, { time: chartTime(end), value: entry }]);
      waveSeriesRef.current.push(line);
      markers.push({ time: chartTime(start), position: scenario.direction === "LONG" ? "belowBar" : "aboveBar",
        color, shape: scenario.direction === "LONG" ? "arrowUp" : "arrowDown",
        text: `${entryResultLabel(result)} · ${scenario.direction}` });
    });
    const sortedMarkers = markers.sort((left, right) => Number(left.time) - Number(right.time));
    if (!markersRef.current) markersRef.current = createSeriesMarkers(candleSeries, sortedMarkers);
    else markersRef.current.setMarkers(sortedMarkers);
  }, [candles, elliottPatterns, entryScenarios, selectedEntryId]);
  const validPatterns = elliottPatterns.filter((pattern) => pattern.state !== "INVALID").length;
  const entries = entryScenarios.filter((scenario) => scenario.setup_type === "ELLIOTT_WAVE3")
    .sort((left,right) => right.created_at-left.created_at);
  return <Paper variant="outlined" sx={{ p: 1, overflow: "hidden" }}><Stack direction="row" sx={{ px: 1, pb: 1, justifyContent: "space-between", alignItems: "center" }}><Typography variant="subtitle2">График актива</Typography><Typography variant="caption" color={validPatterns ? "primary.light" : "text.secondary"}>Elliott: {validPatterns} волн · потенциальных входов: {entries.length}</Typography></Stack><Box ref={ref} sx={{ width: "100%", minHeight: 560 }} />
    <Paper variant="outlined" sx={{ mt: 1, p: 1.5, bgcolor: "rgba(255,255,255,.02)" }}>
      <Typography variant="subtitle2" sx={{ mb: 1 }}>Потенциальные точки входа выбранного актива</Typography>
      {entries.length ? <Stack spacing={.75}>{entries.slice(0,20).map((scenario) => {
        const result = entryResult(scenario,candles); const entry = (scenario.entry_zone_low+scenario.entry_zone_high)/2;
        const focus = () => {
          setSelectedEntryId(scenario.id);
          const duration = Math.max(60_000,scenario.expires_at-scenario.created_at);
          chartRef.current?.timeScale().setVisibleRange({
            from: chartTime(scenario.created_at-duration*.5),
            to: chartTime(scenario.expires_at+duration*.5),
          });
        };
        return <Stack key={scenario.id} direction={{ xs: "column", sm: "row" }} role="button" tabIndex={0}
          onClick={focus} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") focus(); }}
          sx={{ gap: 1, alignItems: { sm: "center" }, py: .75, px: 1, borderBottom: 1,
            borderColor: selectedEntryId === scenario.id ? "primary.main" : "divider", borderRadius: 1,
            cursor: "pointer", bgcolor: selectedEntryId === scenario.id ? "action.selected" : "transparent",
            "&:hover": { bgcolor: "action.hover" }, "&:focus-visible": { outline: "2px solid", outlineColor: "primary.main" } }}>
          <Chip size="small" color={result === "PASSED" ? "success" : result === "WAITING" ? "warning" : "default"} label={entryResultLabel(result)} sx={{ minWidth: 145 }} />
          <Typography variant="body2" color={scenario.direction === "LONG" ? "success.light" : "error.light"} sx={{ minWidth: 55, fontWeight: 700 }}>{scenario.direction}</Typography>
          <Typography variant="body2" sx={{ minWidth: 110 }}>Вход: {entry.toLocaleString("ru-RU",{ maximumFractionDigits: 8 })}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ minWidth: 145 }}>{scenario.entry_model ?? scenario.entry_type ?? "—"}</Typography>
          <Typography variant="caption" color="text.secondary">Сигнал: {formatDubaiTimestamp(scenario.created_at)} · до {formatDubaiTimestamp(scenario.expires_at)}</Typography>
        </Stack>;
      })}</Stack> : <Typography variant="body2" color="text.secondary">Потенциальных входов пока нет.</Typography>}
    </Paper>
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
