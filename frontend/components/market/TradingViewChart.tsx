"use client";

import { Box, Paper, Typography } from "@mui/material";
import { CandlestickSeries, ColorType, createChart, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef } from "react";
import type { Candle } from "../../lib/types";

export function TradingViewChart({ candles }: { candles: Candle[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const seriesRef = useRef<ReturnType<ReturnType<typeof createChart>["addSeries"]> | null>(null);
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
  return <Paper variant="outlined" sx={{ p: 1, overflow: "hidden" }}><Typography variant="subtitle2" sx={{ px: 1, pb: 1 }}>График актива</Typography><Box ref={ref} sx={{ width: "100%", minHeight: 560 }} /></Paper>;
}

function formatDubaiTime(seconds: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Asia/Dubai", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit",
  }).format(new Date(seconds * 1000));
}
