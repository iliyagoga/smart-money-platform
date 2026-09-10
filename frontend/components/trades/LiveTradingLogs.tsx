"use client";

import { Alert, Chip, Stack, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from "@mui/material";
import { useEffect } from "react";
import { useApiResource } from "../../hooks/useApiResource";
import { Panel } from "../ui/Panel";

interface LiveTradingLog {
  id:number;local_order_id?:string;symbol:string;execution_mode:string;event_type:string;
  status:string;details:Record<string,unknown>;created_at:string;
}

export function LiveTradingLogs() {
  const resource=useApiResource<{logs:LiveTradingLog[]}>("/api/v1/exchange/exchange/trading-logs?limit=100");
  const reload=resource.reload;
  useEffect(() => {
    const timer=window.setInterval(reload,15_000);
    return () => window.clearInterval(timer);
  },[reload]);
  const logs=resource.data?.logs ?? [];
  return <Panel title="Журнал live-торговли" meta={`${logs.length} EVENTS`}>
    <Stack spacing={1.5}>
      {resource.error && <Alert severity="error" action={<Typography component="button" onClick={reload}>Повторить</Typography>}>
        {resource.error}
      </Alert>}
      {!logs.length && !resource.isLoading ? <Typography color="text.secondary">Событий live-торговли пока нет.</Typography>
        : <TableContainer><Table size="small" sx={{ minWidth:900 }}><TableHead><TableRow>
          <TableCell>Время</TableCell><TableCell>Режим</TableCell><TableCell>Актив</TableCell>
          <TableCell>Событие</TableCell><TableCell>Статус</TableCell><TableCell>Подробности</TableCell>
        </TableRow></TableHead><TableBody>{logs.map((item) => <TableRow key={item.id} hover>
          <TableCell>{new Date(item.created_at).toLocaleString("ru-RU")}</TableCell>
          <TableCell><Chip size="small" label={item.execution_mode} color={item.execution_mode === "PRODUCTION" ? "error" : "warning"} /></TableCell>
          <TableCell>{item.symbol}</TableCell><TableCell>{item.event_type}</TableCell><TableCell>{item.status}</TableCell>
          <TableCell sx={{ maxWidth:420 }}><Typography variant="caption" sx={{ wordBreak:"break-word" }}>
            {logDetails(item.details)}
          </Typography></TableCell>
        </TableRow>)}</TableBody></Table></TableContainer>}
    </Stack>
  </Panel>;
}

function logDetails(details:Record<string,unknown>) {
  if (typeof details.reason === "string") return details.reason;
  const exchange=details.exchange;
  if (exchange && typeof exchange === "object") {
    const item=exchange as Record<string,unknown>;
    return String(item.sMsg || item.msg || item.ordId || JSON.stringify(item));
  }
  return Object.keys(details).length ? JSON.stringify(details) : "—";
}
