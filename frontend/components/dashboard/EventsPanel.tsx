import { Stack, TablePagination, Typography } from "@mui/material";
import { usePagination } from "../../hooks/usePagination";
import type { PlatformEvent } from "../../lib/types";
import { EmptyState } from "../ui/EmptyState";
import { Panel } from "../ui/Panel";

interface EventsPanelProps { events: PlatformEvent[]; isLive: boolean }

export function EventsPanel({ events, isLive }: EventsPanelProps) {
  const pagination = usePagination(events, 5);
  return (
    <Panel title="Поток событий" meta={isLive ? "LIVE" : "CONNECTING"}>
      {events.length === 0 ? <EmptyState text="Ожидаем новые события" /> : pagination.visible.map((event, index) => (
        <Stack key={`${event.timestamp}-${index}`} direction="row" spacing={2} sx={{ py: 1.5, borderBottom: 1, borderColor: "divider" }}>
          <Typography variant="caption" color="text.secondary" sx={{ width: 90 }}>{new Date(event.timestamp).toLocaleTimeString()}</Typography>
          <Typography variant="caption" sx={{ flex: 1, fontWeight: 700 }}>{event.event_type}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>{event.payload?.symbol ?? event.source}</Typography>
        </Stack>
      ))}
      {events.length > 0 && <TablePagination component="div" {...pagination.paginationProps} />}
    </Panel>
  );
}
