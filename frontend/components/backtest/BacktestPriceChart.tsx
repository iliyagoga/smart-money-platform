"use client";

import { Box, Button, Chip, MenuItem, Paper, Slider, Stack, TextField, Typography } from "@mui/material";
import { useMemo, useRef, useState } from "react";
import type { BacktestChartCandle, BacktestScenario, BacktestTrade } from "../../lib/backtest/types";

const pad = 52;

export function BacktestPriceChart({ candles, candlesByTimeframe, scenarios, trades }: {
  candles: BacktestChartCandle[];
  candlesByTimeframe: Record<string, BacktestChartCandle[]>;
  scenarios: BacktestScenario[];
  trades: BacktestTrade[];
}) {
  const available = Object.keys(candlesByTimeframe);
  const [timeframe, setTimeframe] = useState(available[0] ?? "PRIMARY");
  const [zoom, setZoom] = useState(1);
  const [verticalZoom, setVerticalZoom] = useState(1);
  const [zoneScale, setZoneScale] = useState(1);
  const scrollRef = useRef<HTMLDivElement>(null);
  const selectedCandles = candlesByTimeframe[timeframe] ?? candles;
  const visibleScenarios = useMemo(
    () => available.length ? scenarios.filter((item) => item.timeframe === timeframe) : scenarios,
    [available.length, scenarios, timeframe],
  );
  if (!selectedCandles.length) return null;

  const width = Math.max(1100, selectedCandles.length * 5) * zoom;
  const height = 520 * verticalZoom;
  const start = selectedCandles[0].timestamp;
  const end = selectedCandles[selectedCandles.length - 1].timestamp;
  const prices = selectedCandles.flatMap((item) => [item.high, item.low]);
  visibleScenarios.forEach((item) => prices.push(
    item.entryZoneLow, item.entryZoneHigh, item.stopLossPrice, ...item.takeProfitPrices,
  ));
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const range = high-low || 1;
  const x = (timestamp: number) => pad+(timestamp-start)/Math.max(1,end-start)*(width-pad*2);
  const y = (price: number) => pad+(high-price)/range*(height-pad*2);
  const step = (width-pad*2)/selectedCandles.length;
  const reset = () => {
    setZoom(1); setVerticalZoom(1); setZoneScale(1); scrollRef.current?.scrollTo({ left: 0 });
  };

  return <Paper variant="outlined" sx={{ mt: 1.5, p: 2 }}>
    <Stack direction={{ xs: "column", lg: "row" }} sx={{ justifyContent: "space-between", gap: 1.5, mb: 1.5 }}>
      <div><Typography variant="h6">Интерактивный график SMC</Typography>
        <Typography variant="caption" color="text.secondary">
          Выберите ТФ, увеличьте свечи и зоны, затем перемещайтесь горизонтальной прокруткой.
        </Typography></div>
      <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: .75, alignItems: "center" }}>
        {available.length > 0 && <TextField select size="small" label="Таймфрейм" value={timeframe}
          onChange={(event) => setTimeframe(event.target.value)} sx={{ minWidth: 130 }}>
          {available.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>}
        <Button variant="outlined" onClick={() => setZoom((value) => Math.min(8,value*1.5))}>Приблизить</Button>
        <Button variant="outlined" onClick={() => setZoom((value) => Math.max(.5,value/1.5))}>Отдалить</Button>
        <Button variant="outlined" onClick={reset}>Сбросить</Button>
      </Stack>
    </Stack>
    <Stack direction={{ xs: "column", md: "row" }} spacing={3} sx={{ mb: 1.5, alignItems: "center" }}>
      <Box sx={{ minWidth: 220, flex: 1 }}><Typography variant="caption">Вертикальный масштаб: {verticalZoom.toFixed(1)}×</Typography>
        <Slider min={.75} max={3} step={.25} value={verticalZoom}
          onChange={(_,value) => setVerticalZoom(value as number)} /></Box>
      <Box sx={{ minWidth: 220, flex: 1 }}><Typography variant="caption">Размер зон: {zoneScale.toFixed(1)}×</Typography>
        <Slider min={1} max={8} step={.5} value={zoneScale}
          onChange={(_,value) => setZoneScale(value as number)} /></Box>
      <Stack direction="row" spacing={.75}><Chip size="small" color="success" label="Long" />
        <Chip size="small" color="error" label="Short" />
        <Chip size="small" label={`${visibleScenarios.length} сценариев`} /></Stack>
    </Stack>
    <Box ref={scrollRef} sx={{ overflow: "auto", maxHeight: 900, bgcolor: "#101722", borderRadius: 1 }}>
      <Box component="svg" viewBox={`0 0 ${width} ${height}`} sx={{ display: "block", width, height }}
        aria-label={`График Smart Money ${timeframe}`}>
        {[0,.25,.5,.75,1].map((part) => <g key={part}>
          <line x1={pad} x2={width-pad} y1={pad+(height-pad*2)*part} y2={pad+(height-pad*2)*part}
            stroke="#8793a5" opacity=".2" />
          <text x="4" y={pad+(height-pad*2)*part+4} fill="#aab3c2" fontSize="11">
            {(high-range*part).toFixed(2)}
          </text>
        </g>)}
        {visibleScenarios.map((item) => {
          const color=item.direction === "LONG" ? "#26a69a" : "#ef5350";
          const left=x(item.timestamp); const right=Math.max(left+10,x(Math.min(item.expiresAt,end)));
          const center=(item.entryZoneHigh+item.entryZoneLow)/2;
          const half=Math.max((item.entryZoneHigh-item.entryZoneLow)/2*zoneScale,range*.0015*zoneScale);
          return <g key={item.id}><title>{`${item.templateId} · ${item.direction} · priority ${item.priority}`}</title>
            <rect x={left} y={y(center+half)} width={right-left}
              height={Math.max(4,y(center-half)-y(center+half))} fill={color} opacity=".32"
              stroke={color} strokeWidth="1.5" />
            <line x1={left} x2={right} y1={y(item.stopLossPrice)} y2={y(item.stopLossPrice)}
              stroke="#ff5252" strokeWidth="1.5" strokeDasharray="6 4" />
            {item.takeProfitPrices.map((target) => <line key={target} x1={left} x2={right}
              y1={y(target)} y2={y(target)} stroke="#00e676" strokeDasharray="4 4" />)}
            <text x={left+3} y={Math.max(12,y(center+half)-4)} fill={color} fontSize="11" fontWeight="700">
              {item.templateId}
            </text>
          </g>;
        })}
        {selectedCandles.map((item) => {
          const cx=x(item.timestamp); const color=item.close>=item.open?"#26a69a":"#ef5350";
          return <g key={item.timestamp}><title>{`${new Date(item.timestamp).toLocaleString("ru-RU")} · O ${item.open} H ${item.high} L ${item.low} C ${item.close}`}</title>
            <line x1={cx} x2={cx} y1={y(item.high)} y2={y(item.low)} stroke={color} />
            <rect x={cx-Math.max(1,step*.3)} y={Math.min(y(item.open),y(item.close))}
              width={Math.max(2,step*.6)} height={Math.max(1,Math.abs(y(item.open)-y(item.close)))} fill={color} />
          </g>;
        })}
        {trades.map((trade) => <g key={trade.id}>
          <circle cx={x(trade.entryTime)} cy={y(trade.entryPrice)} r="6"
            fill={trade.direction === "LONG"?"#00e676":"#ff5252"}>
            <title>{`Вход ${trade.direction} ${trade.entryPrice}`}</title>
          </circle>
          <circle cx={x(trade.exitTime)} cy={y(trade.exitPrice)} r="5" fill="#ffd54f">
            <title>{`Выход ${trade.exitPrice}; PnL ${trade.pnl.toFixed(2)}`}</title>
          </circle>
        </g>)}
      </Box>
    </Box>
  </Paper>;
}
