import { Box, Paper, Typography } from "@mui/material";
import type { EquityPoint } from "../../lib/backtest/types";

export function EquityChart({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) return null;
  const width = 1000;
  const height = 280;
  const padding = 24;
  let min = points[0].equity;
  let max = points[0].equity;
  for (const point of points) {
    min = Math.min(min, point.equity);
    max = Math.max(max, point.equity);
  }
  const maximumRenderedPoints = 2_000;
  const step = Math.max(1, Math.ceil(points.length / maximumRenderedPoints));
  const renderedPoints = points.filter((_, index) => index % step === 0 || index === points.length - 1);
  const range = max - min || 1;
  const duration = points.at(-1)!.timestamp - points[0].timestamp || 1;
  const path = renderedPoints.map((point, index) => {
    const x = padding + (point.timestamp - points[0].timestamp) / duration * (width - padding * 2);
    const y = padding + (max - point.equity) / range * (height - padding * 2);
    return `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");

  return <Paper variant="outlined" sx={{ mt: 1.5, p: 2.5 }}>
    <Typography variant="h6" sx={{ mb: 1 }}>Кривая капитала</Typography>
    <Box component="svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Кривая капитала" sx={{ display: "block", width: "100%" }}>
      <defs>
        <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#62d99b" stopOpacity="0.3" />
          <stop offset="1" stopColor="#62d99b" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L${width - padding},${height - padding} L${padding},${height - padding} Z`} fill="url(#equity-fill)" />
      <path d={path} fill="none" stroke="#168653" strokeWidth="3" />
    </Box>
  </Paper>;
}
