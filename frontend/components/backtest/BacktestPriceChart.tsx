import { Box, Chip, Paper, Stack, Typography } from "@mui/material";
import type { BacktestChartCandle, BacktestScenario, BacktestTrade } from "../../lib/backtest/types";

const height = 520;
const pad = 44;

export function BacktestPriceChart({ candles, scenarios, trades }: {
  candles: BacktestChartCandle[]; scenarios: BacktestScenario[]; trades: BacktestTrade[];
}) {
  if (!candles.length) return null;
  const width = Math.max(1100, candles.length * 4);
  const start = candles[0].timestamp;
  const end = candles[candles.length - 1].timestamp;
  const prices = candles.flatMap((item) => [item.high, item.low]);
  scenarios.forEach((item) => prices.push(item.entryZoneLow, item.entryZoneHigh, item.stopLossPrice, ...item.takeProfitPrices));
  const low = Math.min(...prices);
  const high = Math.max(...prices);
  const range = high - low || 1;
  const x = (timestamp: number) => pad + (timestamp - start) / Math.max(1, end - start) * (width - pad * 2);
  const y = (price: number) => pad + (high - price) / range * (height - pad * 2);
  const step = (width - pad * 2) / candles.length;

  return <Paper variant="outlined" sx={{ mt: 1.5, p: 2 }}>
    <Stack direction={{ xs: "column", md: "row" }} sx={{ justifyContent: "space-between", gap: 1, mb: 1 }}>
      <div><Typography variant="h6">График SMC-разметки</Typography>
        <Typography variant="caption" color="text.secondary">Свечи, зоны входа, SL/TP и фактические сделки. Прокрутите график по горизонтали.</Typography></div>
      <Stack direction="row" spacing={0.75}><Chip size="small" color="success" label="Long" /><Chip size="small" color="error" label="Short" /><Chip size="small" label={`${scenarios.length} сценариев`} /></Stack>
    </Stack>
    <Box sx={{ overflowX: "auto", bgcolor: "#101722", borderRadius: 1 }}>
      <Box component="svg" viewBox={`0 0 ${width} ${height}`} sx={{ display: "block", width, height }} aria-label="Свечной график результатов Smart Money">
        {[0, .25, .5, .75, 1].map((part) => <line key={part} x1={pad} x2={width-pad} y1={pad+(height-pad*2)*part} y2={pad+(height-pad*2)*part} stroke="#8793a5" opacity=".16" />)}
        {scenarios.map((item) => {
          const color = item.direction === "LONG" ? "#26a69a" : "#ef5350";
          const left = x(item.timestamp);
          const right = Math.max(left + 6, x(Math.min(item.expiresAt, end)));
          return <g key={item.id}>
            <title>{`${item.templateId} · приоритет ${item.priority} · ${item.direction} ${(item.confidence*100).toFixed(0)}%\n${item.reasons.join(" · ")}`}</title>
            <rect
              x={left}
              y={y(item.entryZoneHigh)}
              width={right-left}
              height={Math.max(2,y(item.entryZoneLow)-y(item.entryZoneHigh))}
              fill={color}
              opacity=".2"
            />
            <line x1={left} x2={right} y1={y(item.stopLossPrice)} y2={y(item.stopLossPrice)} stroke="#ef5350" strokeDasharray="5 4" />
            {item.takeProfitPrices.map((target) => <line key={target} x1={left} x2={right} y1={y(target)} y2={y(target)} stroke="#26a69a" strokeDasharray="3 4" />)}
            <text x={left+2} y={Math.max(12,y(item.entryZoneHigh)-3)} fill={color} fontSize="10">
              {item.templateId}
            </text>
          </g>;
        })}
        {candles.map((item) => {
          const cx=x(item.timestamp); const positive=item.close>=item.open; const color=positive?"#26a69a":"#ef5350";
          return <g key={item.timestamp}>
            <title>{`${new Date(item.timestamp).toLocaleString("ru-RU")} O ${item.open} H ${item.high} L ${item.low} C ${item.close}`}</title>
            <line x1={cx} x2={cx} y1={y(item.high)} y2={y(item.low)} stroke={color} />
            <rect
              x={cx-Math.max(1,step*.3)} y={Math.min(y(item.open),y(item.close))}
              width={Math.max(2,step*.6)} height={Math.max(1,Math.abs(y(item.open)-y(item.close)))} fill={color}
            />
          </g>;
        })}
        {trades.map((trade) => <g key={trade.id}>
          <circle cx={x(trade.entryTime)} cy={y(trade.entryPrice)} r="5" fill={trade.direction === "LONG" ? "#00e676" : "#ff5252"}>
            <title>{`Вход ${trade.direction} ${trade.entryPrice}`}</title>
          </circle>
          <circle cx={x(trade.exitTime)} cy={y(trade.exitPrice)} r="4" fill="#ffd54f">
            <title>{`Выход ${trade.exitPrice}, PnL ${trade.pnl.toFixed(2)}`}</title>
          </circle>
        </g>)}
      </Box>
    </Box>
  </Paper>;
}
