import { Button, Chip, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TablePagination, TableRow, Typography } from "@mui/material";
import { usePagination } from "../../hooks/usePagination";
import type { TradingOrder } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";
import { Panel } from "../ui/Panel";

export function OrdersPanel({ orders, canCancel, onCancel }: {
  orders: TradingOrder[]; canCancel: boolean; onCancel: (order: TradingOrder) => void;
}) {
  const pagination = usePagination(orders);
  return <Panel title="Ордера Elliott" meta={`${orders.length} ORDERS`}>
    {orders.length === 0 ? <EmptyState text="Ордеров пока нет" /> : <TableContainer><Table size="small" sx={{ minWidth: 900 }}><TableHead><TableRow>
      <TableCell>Время</TableCell><TableCell>Актив</TableCell><TableCell>Сторона</TableCell><TableCell>Тип</TableCell>
      <TableCell>Цена</TableCell><TableCell>Количество</TableCell><TableCell>Статус / причина</TableCell><TableCell align="right">Действие</TableCell>
    </TableRow></TableHead><TableBody>{pagination.visible.map((order) => <TableRow hover key={order.id}>
      <TableCell>{new Date(order.created_at).toLocaleString("ru-RU")}</TableCell><TableCell>{order.symbol}</TableCell>
      <TableCell>{order.side}</TableCell><TableCell>{order.type}</TableCell><TableCell>{order.filled_price ?? order.price ?? "market"}</TableCell>
      <TableCell>{order.quantity}</TableCell><TableCell><Stack spacing={.5}><Chip size="small" label={order.status} variant="outlined" sx={{ alignSelf:"flex-start" }} />
        {order.rejection_reason && <Typography variant="caption" color="error.main" sx={{ maxWidth:360 }}>{order.rejection_reason}</Typography>}
      </Stack></TableCell>
      <TableCell align="right"><Button size="small" color="error" disabled={!canCancel || !["PENDING", "OPEN", "SUBMITTING", "PARTIALLY_FILLED"].includes(order.status)}
        onClick={() => onCancel(order)}>Отменить</Button></TableCell>
    </TableRow>)}</TableBody></Table></TableContainer>}{orders.length > 0 && <TablePagination component="div" {...pagination.paginationProps} />}
  </Panel>;
}
