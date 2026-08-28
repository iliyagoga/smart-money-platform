"use client";

import { Box, Button, Chip, CircularProgress, FormControlLabel, MenuItem, Pagination, Paper, Stack, Switch, TextField, Typography } from "@mui/material";
import { BaselineSeries, CandlestickSeries, ColorType, HistogramSeries, LineSeries, LineType, createChart, createSeriesMarkers, type IChartApi, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import type { BacktestChartCandle, BacktestScenario, BacktestStructureOverlay, BacktestTrade } from "../../lib/backtest/types";

const chartTime = (timestamp: number) => Math.floor(timestamp/1000) as UTCTimestamp;

const candleTimeForMarker = (timestamp: number, candles: BacktestChartCandle[]) => {
  if (!candles.length || timestamp < candles[0].timestamp || timestamp > candles[candles.length-1].timestamp) return undefined;
  let low = 0;
  let high = candles.length-1;
  while (low < high) {
    const middle = Math.ceil((low+high)/2);
    if (candles[middle].timestamp <= timestamp) low = middle;
    else high = middle-1;
  }
  return chartTime(candles[low].timestamp);
};

export function BacktestPriceChart({ candles, candlesByTimeframe, overlaysByTimeframe, scenarios, trades }: {
  candles: BacktestChartCandle[];
  candlesByTimeframe: Record<string, BacktestChartCandle[]>;
  overlaysByTimeframe: Record<string, BacktestStructureOverlay>;
  scenarios: BacktestScenario[];
  trades: BacktestTrade[];
}) {
  const available = Object.keys(candlesByTimeframe);
  const [timeframe, setTimeframe] = useState(available[0] ?? "PRIMARY");
  const [selectedScenario, setSelectedScenario] = useState("ALL");
  const [direction, setDirection] = useState<"ALL" | "LONG" | "SHORT">("ALL");
  const [visibleTemplates, setVisibleTemplates] = useState<string[]>([]);
  const [zoneLimit, setZoneLimit] = useState(100);
  const [zonePage, setZonePage] = useState(1);
  const [showEntryZones, setShowEntryZones] = useState(false);
  const [showFractals, setShowFractals] = useState(true);
  const [showBos, setShowBos] = useState(true);
  const [showOrderBlocks, setShowOrderBlocks] = useState(true);
  const [showFvgs, setShowFvgs] = useState(true);
  const [showStops, setShowStops] = useState(true);
  const [showTargets, setShowTargets] = useState(true);
  const [showTrades, setShowTrades] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const [showAtr, setShowAtr] = useState(false);
  const [showAdx, setShowAdx] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const fullscreenRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fitRef = useRef<(scenario?: BacktestScenario) => void>(() => undefined);
  const selectedCandles = candlesByTimeframe[timeframe] ?? candles;
  const selectedOverlay = overlaysByTimeframe[timeframe];
  const timeframeScenarios = useMemo(
    () => available.length ? scenarios.filter((item) => item.timeframe === timeframe) : scenarios,
    [available.length, scenarios, timeframe],
  );
  const scenarioTimeframes = useMemo(
    () => new Map(scenarios.map((item) => [item.id, item.timeframe])),
    [scenarios],
  );
  const scenariosById = useMemo(() => new Map(scenarios.map((item) => [item.id, item])), [scenarios]);
  const visibleTrades = useMemo(() => trades.filter((trade) => {
    if (selectedScenario !== "ALL" && trade.scenarioId !== selectedScenario) return false;
    if (!available.length || !trade.scenarioId) return true;
    return scenarioTimeframes.get(trade.scenarioId) === timeframe;
  }), [available.length, scenarioTimeframes, selectedScenario, timeframe, trades]);
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
    if (selectedOverlay && showFractals && selectedOverlay.swings.length > 1) {
      const fractals = activeChart.addSeries(LineSeries, {
        color: "rgba(255,255,255,.72)", lineWidth: 1, lineStyle: 2, title: "Fractals",
        lastValueVisible: false, priceLineVisible: false,
      });
      fractals.setData(selectedOverlay.swings
        .filter((item) => item.timestamp >= selectedCandles[0].timestamp && item.timestamp <= selectedCandles[selectedCandles.length-1].timestamp)
        .map((item) => ({ time: chartTime(item.timestamp), value: item.price })));
    }
    if (selectedOverlay && showBos) {
      (["BULLISH", "BEARISH"] as const).forEach((direction) => {
        const points = selectedOverlay.changes.filter((item) => item.direction === direction
          && item.timestamp >= selectedCandles[0].timestamp && item.timestamp <= selectedCandles[selectedCandles.length-1].timestamp);
        if (!points.length) return;
        const bos = activeChart.addSeries(LineSeries, {
          color: direction === "BULLISH" ? "rgba(80,220,140,.78)" : "rgba(255,82,82,.78)",
          lineWidth: 1, lineType: LineType.WithSteps, title: `${direction === "BULLISH" ? "Long" : "Short"} BOS`,
          lastValueVisible: false, priceLineVisible: false,
        });
        bos.setData(points.map((item) => ({ time: chartTime(item.timestamp), value: item.price })));
      });
    }
    const renderZones = (zones: Array<{ id: string; timestamp: number; low: number; high: number; direction: "BULLISH" | "BEARISH"; endAt?: number }>, kind: "OB" | "FVG") => {
      zones.slice(-150).forEach((zone) => {
        const start = Math.max(zone.timestamp, selectedCandles[0].timestamp);
        const end = Math.min(zone.endAt ?? selectedCandles[selectedCandles.length-1].timestamp, selectedCandles[selectedCandles.length-1].timestamp);
        if (start >= end) return;
        const bullish = zone.direction === "BULLISH";
        const color = kind === "OB" ? (bullish ? "rgba(40,200,110,.22)" : "rgba(240,65,65,.22)")
          : (bullish ? "rgba(35,150,255,.22)" : "rgba(175,80,220,.24)");
        const line = kind === "OB" ? (bullish ? "rgba(40,220,120,.7)" : "rgba(255,75,75,.7)")
          : (bullish ? "rgba(50,165,255,.75)" : "rgba(190,90,235,.78)");
        const zoneSeries = activeChart.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: zone.low }, topFillColor1: color, topFillColor2: color,
          topLineColor: line, bottomFillColor1: color, bottomFillColor2: color, bottomLineColor: line,
          lineWidth: 1, title: `${kind} ${bullish ? "LONG" : "SHORT"}`, lastValueVisible: false, priceLineVisible: false,
        });
        zoneSeries.setData([{ time: chartTime(start), value: zone.high }, { time: chartTime(end), value: zone.high }]);
      });
    };
    if (selectedOverlay && showOrderBlocks) renderZones(selectedOverlay.orderBlocks, "OB");
    if (selectedOverlay && showFvgs) renderZones(selectedOverlay.fvgs, "FVG");
    let indicatorPane = 1;
    if (showVolume) {
      const volumeSeries = activeChart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" }, priceScaleId: "volume", title: "Volume",
      }, indicatorPane++);
      volumeSeries.setData(selectedCandles.map((item) => ({
        time: chartTime(item.timestamp), value: item.volume,
        color: item.close >= item.open ? "rgba(38,166,154,.55)" : "rgba(239,83,80,.55)",
      })));
    }
    if (showAtr) {
      const atrSeries = activeChart.addSeries(LineSeries, { color: "#ffb74d", lineWidth: 2, title: "ATR(14)" }, indicatorPane++);
      atrSeries.setData(selectedCandles.flatMap((item) => item.indicators?.["atr:14"] === undefined ? [] : [
        { time: chartTime(item.timestamp), value: item.indicators["atr:14"] },
      ]));
    }
    if (showAdx) {
      const adxSeries = activeChart.addSeries(LineSeries, { color: "#ab47bc", lineWidth: 2, title: "ADX(14)" }, indicatorPane++);
      adxSeries.setData(selectedCandles.flatMap((item) => item.indicators?.["adx:14"] === undefined ? [] : [
        { time: chartTime(item.timestamp), value: item.indicators["adx:14"] },
      ]));
    }
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
      if (showTargets) scenario.takeProfitPrices.slice(0, 1).forEach((target) => {
        const takeProfit = activeChart.addSeries(LineSeries, {
          color: "#00c853", lineWidth: 1, lineStyle: 2, title: "TP",
        });
        takeProfit.setData([{ time: chartTime(scenario.timestamp), value: target }, { time: chartTime(end), value: target }]);
      });
    });
    if (showTrades) visibleTrades.forEach((trade) => {
      const scenario = trade.scenarioId ? scenariosById.get(trade.scenarioId) : undefined;
      const target = scenario?.takeProfitPrices[0];
      const stop = scenario?.stopLossPrice;
      if (target === undefined || stop === undefined) return;
      const from = Math.max(trade.entryTime, selectedCandles[0].timestamp);
      const to = Math.min(trade.exitTime, selectedCandles[selectedCandles.length-1].timestamp);
      if (from >= to) return;
      const addTradeZone = (price: number, color: string, title: string) => {
        const zone = activeChart.addSeries(BaselineSeries, {
          baseValue: { type: "price", price: trade.entryPrice },
          topFillColor1: color, topFillColor2: color, bottomFillColor1: color, bottomFillColor2: color,
          topLineColor: color, bottomLineColor: color,
          lineWidth: 1, title, lastValueVisible: false, priceLineVisible: false,
        });
        zone.setData([{ time: chartTime(from), value: price }, { time: chartTime(to), value: price }]);
      };
      addTradeZone(stop, "rgba(239, 83, 80, .28)", `${trade.direction} #${trade.id} SL`);
      addTradeZone(target, "rgba(0, 200, 83, .24)", `${trade.direction} #${trade.id} TP`);
    });
    const markers = showTrades ? visibleTrades.flatMap((trade) => {
      const entryTime = candleTimeForMarker(trade.entryTime, selectedCandles);
      const exitTime = candleTimeForMarker(trade.exitTime, selectedCandles);
      return [
        entryTime === undefined ? undefined : {
          time: entryTime, position: trade.direction === "LONG" ? "belowBar" as const : "aboveBar" as const,
          color: trade.direction === "LONG" ? "#00e676" : "#ff5252", shape: trade.direction === "LONG" ? "arrowUp" as const : "arrowDown" as const,
          text: `${trade.direction} #${trade.id}`,
        },
        exitTime === undefined ? undefined : {
          time: exitTime, position: "inBar" as const, color: trade.pnl >= 0 ? "#ffd54f" : "#ff9800",
          shape: "circle" as const, text: `Exit ${trade.pnl.toFixed(2)}`,
        },
      ].filter((item) => item !== undefined);
    }).sort((left,right) => Number(left.time)-Number(right.time)) : [];
    createSeriesMarkers(candleSeries, markers);
    activeChart.timeScale().fitContent();
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
  }, [scenariosById, selectedCandles, selectedOverlay, selectedScenario, showAdx, showAtr, showBos, showEntryZones, showFractals, showFvgs, showOrderBlocks, showStops, showTargets, showTrades, showVolume, visibleScenarios, visibleTrades]);

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
          onChange={(event) => { setIsRendering(true); setTimeframe(event.target.value); setSelectedScenario("ALL"); }} sx={{ minWidth: 125 }}>
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
        <FormControlLabel control={<Switch size="small" checked={showFractals} onChange={(_,value) => setShowFractals(value)} />} label="Фракталы" />
        <FormControlLabel control={<Switch size="small" checked={showBos} onChange={(_,value) => setShowBos(value)} />} label="BOS" />
        <FormControlLabel control={<Switch size="small" checked={showOrderBlocks} onChange={(_,value) => setShowOrderBlocks(value)} />} label="Order Blocks" />
        <FormControlLabel control={<Switch size="small" checked={showFvgs} onChange={(_,value) => setShowFvgs(value)} />} label="FVG" />
        <FormControlLabel control={<Switch size="small" checked={showStops} onChange={(_,value) => setShowStops(value)} />} label="Stop Loss" />
        <FormControlLabel control={<Switch size="small" checked={showTargets} onChange={(_,value) => setShowTargets(value)} />} label="Take Profit" />
        <FormControlLabel control={<Switch size="small" checked={showTrades} onChange={(_,value) => setShowTrades(value)} />} label="Сделки" />
        <FormControlLabel control={<Switch size="small" checked={showVolume} onChange={(_,value) => setShowVolume(value)} />} label="Объём" />
        <FormControlLabel control={<Switch size="small" checked={showAtr} onChange={(_,value) => setShowAtr(value)} />} label="ATR(14)" />
        <FormControlLabel control={<Switch size="small" checked={showAdx} onChange={(_,value) => setShowAdx(value)} />} label="ADX(14)" />
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
      <Chip size="small" label={`${visibleTrades.length} сделок показано · ${trades.length} всего`} /></Stack>
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
