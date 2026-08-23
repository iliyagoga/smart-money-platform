"use client";

import { Chip, Paper, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { EventSocket } from "../../lib/socket";
import type { PlatformEvent } from "../../lib/types";

export default function MarketPage() {
  const [events, setEvents] = useState<PlatformEvent[]>([]);
  const [isLive, setIsLive] = useState(false);

  useEffect(() => {
    const socket = new EventSocket();
    socket.subscribe((event) => {
      setIsLive(true);
      setEvents((current) => [event, ...current].slice(0, 50));
    });
    void socket.connect();
    return () => socket.close();
  }, []);

  return (
    <SectionPage title="Рынок" description="События рынка и изменения структуры в реальном времени.">
      <Stack direction="row" sx={{ mb: 2, justifyContent: "flex-end" }}>
        <Chip label={isLive ? "Поток подключён" : "Подключение…"} color={isLive ? "success" : "default"} variant="outlined" />
      </Stack>
      {events.length === 0 ? <EmptyState text="Ожидаем рыночные события" /> : <Stack spacing={1}>{events.map((event, index) => (
        <Paper key={`${event.timestamp}-${index}`} variant="outlined" sx={{ p: 2 }}>
          <Stack direction={{ xs: "column", sm: "row" }} sx={{ justifyContent: "space-between", gap: 1 }}>
            <Typography sx={{ fontWeight: 650 }}>{event.event_type}</Typography>
            <Typography variant="caption" color="text.secondary">{new Date(event.timestamp).toLocaleString("ru-RU")}</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>{event.payload?.symbol ?? event.source ?? "Общее событие"}</Typography>
        </Paper>
      ))}</Stack>}
    </SectionPage>
  );
}
