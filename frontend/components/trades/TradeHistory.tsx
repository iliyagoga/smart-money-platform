import { Chip, Paper, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Typography } from "@mui/material";
import { useState } from "react";
import type { ClosedTrade } from "../../lib/types";
import { formatSignedMoney } from "../../lib/formatters";
import { EmptyState } from "../ui/EmptyState";

export function TradeHistory({ trades }: { trades: ClosedTrade[] }) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const visibleTrades = trades.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);
  return <Paper variant="outlined" sx={{ mt: 1.5, p: { xs: 1, md: 2.5 } }}>
    <Typography variant="h6" sx={{ px: 1, pb: 2 }}>Список сделок · {trades.length}</Typography>
    {trades.length === 0 ? <EmptyState text="Закрытых сделок пока нет" /> : <TableContainer><Table size="small">
      <TableHead><TableRow><TableCell>Дата</TableCell><TableCell>Инструмент</TableCell><TableCell>Сторона</TableCell>
        <TableCell>Вход</TableCell><TableCell>Выход</TableCell><TableCell>PnL</TableCell><TableCell>Причина</TableCell>
      </TableRow></TableHead>
      <TableBody>{visibleTrades.map((trade) => <TableRow hover key={trade.position_id}>
        <TableCell>{new Date(trade.closed_at).toLocaleString("ru-RU")}</TableCell><TableCell>{trade.symbol}</TableCell>
        <TableCell>{trade.direction}</TableCell><TableCell>{trade.entry_price}</TableCell><TableCell>{trade.exit_price}</TableCell>
        <TableCell sx={{ color: trade.pnl >= 0 ? "success.main" : "error.main", fontWeight: 700 }}>{formatSignedMoney(trade.pnl)}</TableCell>
        <TableCell><Chip label={trade.reason} size="small" variant="outlined" /></TableCell>
      </TableRow>)}</TableBody>
    </Table><TablePagination component="div" count={trades.length} page={page} rowsPerPage={rowsPerPage}
      rowsPerPageOptions={[10, 25, 50]} labelRowsPerPage="Строк" onPageChange={(_, value) => setPage(value)}
      onRowsPerPageChange={(event) => { setRowsPerPage(Number(event.target.value)); setPage(0); }} /></TableContainer>}
  </Paper>;
}
