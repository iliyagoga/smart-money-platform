import { Button, Table, TableBody, TableCell, TableHead, TableRow } from "@mui/material";
import type { Position } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";
import { Panel } from "../ui/Panel";

interface PositionsPanelProps {
  canClose?: boolean;
  closingId?: string;
  onClose?: (position: Position) => void;
  positions: Position[];
}

export function PositionsPanel({ canClose = false, closingId = "", onClose, positions }: PositionsPanelProps) {
  return (
    <Panel title="Открытые позиции" meta={`${positions.length} ACTIVE`}>
      {positions.length === 0 ? <EmptyState text="Открытых позиций нет" /> : (
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Инструмент</TableCell><TableCell>Направление</TableCell><TableCell>Вход</TableCell>
            <TableCell>Количество</TableCell><TableCell>Статус</TableCell>
            {canClose && <TableCell align="right">Действие</TableCell>}
          </TableRow></TableHead>
          <TableBody>{positions.map((position) => (
            <TableRow key={position.id}>
              <TableCell>{position.symbol}</TableCell>
              <TableCell sx={{ color: position.direction === "LONG" ? "success.main" : "error.main" }}>{position.direction}</TableCell>
              <TableCell>{position.entry_price}</TableCell><TableCell>{position.quantity}</TableCell><TableCell>{position.status}</TableCell>
              {canClose && <TableCell align="right">
                <Button
                  variant="outlined"
                  color="error"
                  size="small"
                  disabled={closingId === position.id}
                  onClick={() => onClose?.(position)}
                >
                  {closingId === position.id ? "Закрываем…" : "Закрыть"}
                </Button>
              </TableCell>}
            </TableRow>
          ))}</TableBody>
        </Table>
      )}
    </Panel>
  );
}
