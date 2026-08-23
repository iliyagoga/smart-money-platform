import { Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import type { ClosedTrade } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";

export function TradeHistory({ trades }: { trades: ClosedTrade[] }) {
  return <Paper variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
    <Typography variant="h6" sx={{ px: 1, pb: 2 }}>История сделок</Typography>
    {trades.length === 0 ? <EmptyState text="Закрытых сделок пока нет" /> : <TableContainer><Table size="small">
      <TableHead><TableRow><TableCell>Дата</TableCell><TableCell>Инструмент</TableCell><TableCell>Сторона</TableCell>
        <TableCell>Вход</TableCell><TableCell>Выход</TableCell><TableCell>PnL</TableCell><TableCell>Причина</TableCell>
      </TableRow></TableHead>
      <TableBody>{trades.map((trade) => <TableRow key={trade.position_id}>
        <TableCell>{new Date(trade.closed_at).toLocaleString("ru-RU")}</TableCell><TableCell>{trade.symbol}</TableCell>
        <TableCell>{trade.direction}</TableCell><TableCell>{trade.entry_price}</TableCell><TableCell>{trade.exit_price}</TableCell>
        <TableCell sx={{ color: trade.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{trade.pnl.toFixed(2)}</TableCell>
        <TableCell><Chip label={trade.reason} size="small" variant="outlined" /></TableCell>
      </TableRow>)}</TableBody>
    </Table></TableContainer>}
  </Paper>;
}
