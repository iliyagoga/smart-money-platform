"use client";

import { Box, Paper, Stack, Typography } from "@mui/material";
import { CandlestickSeries, ColorType, LineSeries, createChart, createSeriesMarkers, type ISeriesMarkersPluginApi, type SeriesMarker, type Time, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Candle } from "../../lib/types";

export interface LiveElliottPoint { timestamp: number; confirmed_at: number; price: number; kind: "HIGH" | "LOW" }
export interface LiveElliottPattern {
  id: string; direction: "LONG" | "SHORT"; state: string; invalid_reason?: string; signal_time?: number;
  structure_timeframe: string; entry_timeframe: string; points: Record<string, LiveElliottPoint>;
}

export function TradingViewChart({ candles, elliottPatterns = [] }: { candles: Candle[]; elliottPatterns?: LiveElliottPattern[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>["addSeries"]> | null>(null);
  const waveSeriesRef = useRef<Array<ReturnType<ReturnType<typeof createChart>["addSeries"]>>>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const hasDataRef = useRef(false);
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
      const wave = chart.addSeries(LineSeries, { color, lineWidth: 3, priceLineVisible: false,
        lastValueVisible: false, title: `Elliott ${pattern.structure_timeframe}` });
      wave.setData(points.map((point) => ({
        time: chartTime(nearestTimestamp(orderedCandles, point.confirmed_at)), value: point.price,
      })));
      waveSeriesRef.current.push(wave);
      points.forEach((point) => markers.push({
        time: chartTime(nearestTimestamp(orderedCandles, point.confirmed_at)),
        position: point.kind === "LOW" ? "belowBar" : "aboveBar", color, shape: "circle",
        text: `${point.label} · ${pattern.structure_timeframe}`,
      }));
    });
    const sortedMarkers = markers.sort((left, right) => Number(left.time) - Number(right.time));
    if (!markersRef.current) markersRef.current = createSeriesMarkers(candleSeries, sortedMarkers);
    else markersRef.current.setMarkers(sortedMarkers);
  }, [candles, elliottPatterns]);
  const validPatterns = elliottPatterns.filter((pattern) => pattern.state !== "INVALID").length;
  return <Paper variant="outlined" sx={{ p: 1, overflow: "hidden" }}><Stack direction="row" sx={{ px: 1, pb: 1, justifyContent: "space-between", alignItems: "center" }}><Typography variant="subtitle2">График актива</Typography><Typography variant="caption" color={validPatterns ? "primary.light" : "text.secondary"}>Elliott: {validPatterns} волн</Typography></Stack><Box ref={ref} sx={{ width: "100%", minHeight: 560 }} /></Paper>;
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
