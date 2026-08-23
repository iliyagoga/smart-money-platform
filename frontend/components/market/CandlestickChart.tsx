import { Box, Paper, Stack, Typography } from "@mui/material";
import type { Candle, MarketStructure } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";

interface CandlestickChartProps {
  candles: Candle[];
  structure?: MarketStructure;
}

const chartWidth = 1000;
const chartHeight = 420;
const padding = 36;

export function CandlestickChart({ candles, structure }: CandlestickChartProps) {
  const visibleCandles = [...candles].sort((left, right) => left.timestamp - right.timestamp).slice(-100);
  if (visibleCandles.length === 0) return <EmptyState text="Свечные данные пока отсутствуют" />;

  const zones = [...(structure?.order_blocks ?? []), ...(structure?.fvgs ?? [])];
  const prices = visibleCandles.flatMap((candle) => [candle.high, candle.low]);
  zones.forEach((zone) => prices.push(zone.zone_high, zone.zone_low));
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;
  const plotHeight = chartHeight - padding * 2;
  const candleStep = (chartWidth - padding * 2) / visibleCandles.length;
  const candleWidth = Math.max(2, candleStep * 0.58);
  const y = (price: number) => padding + ((maxPrice - price) / priceRange) * plotHeight;

  return (
    <Paper variant="outlined" sx={{ p: { xs: 1, md: 2.5 }, overflow: "hidden" }}>
      <Stack direction="row" sx={{ px: 1, pb: 1.5, justifyContent: "space-between" }}>
        <Typography variant="subtitle2">Цена и зоны SMC</Typography>
        <Typography variant="caption" color="text.secondary">{minPrice.toFixed(2)} — {maxPrice.toFixed(2)}</Typography>
      </Stack>
      <Box sx={{ width: "100%", overflowX: "auto" }}>
        <Box
          component="svg"
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          role="img"
          aria-label="Свечной график"
          sx={{ display: "block", minWidth: 720 }}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((part) => {
            const lineY = padding + plotHeight * part;
            return <line key={part} x1={padding} x2={chartWidth - padding} y1={lineY} y2={lineY} stroke="currentColor" opacity="0.08" />;
          })}
          {zones.map((zone) => (
            <rect
              key={zone.id}
              x={padding}
              y={y(zone.zone_high)}
              width={chartWidth - padding * 2}
              height={Math.max(2, y(zone.zone_low) - y(zone.zone_high))}
              fill={zone.type.includes("BULL") ? "#62d99b" : "#ff6b6b"}
              opacity="0.1"
            />
          ))}
          {visibleCandles.map((candle, index) => {
            const x = padding + index * candleStep + candleStep / 2;
            const isPositive = candle.close >= candle.open;
            const color = isPositive ? "#168653" : "#d94a4a";
            return (
              <g key={`${candle.timestamp}-${index}`}>
                <title>{new Date(candle.timestamp).toLocaleString("ru-RU")} · O {candle.open} H {candle.high} L {candle.low} C {candle.close}</title>
                <line x1={x} x2={x} y1={y(candle.high)} y2={y(candle.low)} stroke={color} strokeWidth="1.5" />
                <rect
                  x={x - candleWidth / 2}
                  y={Math.min(y(candle.open), y(candle.close))}
                  width={candleWidth}
                  height={Math.max(2, Math.abs(y(candle.open) - y(candle.close)))}
                  fill={color}
                  rx="1"
                />
              </g>
            );
          })}
        </Box>
      </Box>
    </Paper>
  );
}
