import { Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";
import type { Position } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";
import { Panel } from "../ui/Panel";

export function PositionsPanel({ positions }: { positions: Position[] }) {
  return (
    <Panel title="Открытые позиции" meta={`${positions.length} ACTIVE`}>
      {positions.length === 0 ? <EmptyState text="Открытых позиций нет" /> : (
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Инструмент</TableCell><TableCell>Направление</TableCell><TableCell>Вход</TableCell>
            <TableCell>Количество</TableCell><TableCell>Статус</TableCell>
          </TableRow></TableHead>
          <TableBody>{positions.map((position) => (
            <TableRow key={position.id}>
              <TableCell>{position.symbol}</TableCell>
              <TableCell sx={{ color: position.direction === "LONG" ? "success.main" : "error.main" }}>{position.direction}</TableCell>
              <TableCell>{position.entry_price}</TableCell><TableCell>{position.quantity}</TableCell><TableCell>{position.status}</TableCell>
            </TableRow>
          ))}</TableBody>
        </Table>
      )}
    </Panel>
  );
}
