"use client";

import { Box, Container, Grid, Stack, Typography } from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { keycloak } from "../lib/auth";
import { EventSocket } from "../lib/socket";
import type { PlatformEvent, Portfolio, Position, PositionsResponse, ServiceStatus, ServicesResponse } from "../lib/types";
import { DashboardHeader } from "./dashboard/DashboardHeader";
import { EventsPanel } from "./dashboard/EventsPanel";
import { MetricsGrid } from "./dashboard/MetricsGrid";
import { PositionsPanel } from "./dashboard/PositionsPanel";
import { ServicesPanel } from "./dashboard/ServicesPanel";
import { SignalPanel } from "./dashboard/SignalPanel";

export default function Dashboard() {
  const [portfolio, setPortfolio] = useState<Portfolio>();
  const [services, setServices] = useState<ServiceStatus[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);
  const [events, setEvents] = useState<PlatformEvent[]>([]);
  const [isLive, setIsLive] = useState(false);
  const username = String(keycloak().tokenParsed?.preferred_username ?? "пользователь");

  const loadDashboard = useCallback(async () => {
    const [portfolioData, servicesData, positionsData] = await Promise.all([
      api<Portfolio>("/api/v1/analytics/portfolio"),
      api<ServicesResponse>("/api/v1/analytics/monitoring/services"),
      api<PositionsResponse | Position[]>("/api/v1/execution/positions"),
    ]);
    setPortfolio(portfolioData);
    setServices(servicesData.services ?? []);
    setPositions(Array.isArray(positionsData) ? positionsData : (positionsData.positions ?? []));
  }, []);

  useEffect(() => {
    void loadDashboard().catch(console.error);
    const socket = new EventSocket();
    socket.subscribe((event) => {
      setIsLive(true);
      setEvents((currentEvents) => [event, ...currentEvents].slice(0, 8));
      if (event.event_type.startsWith("position.")) void loadDashboard().catch(console.error);
    });
    void socket.connect();
    return () => socket.close();
  }, [loadDashboard]);

  return (
    <Container component="main" maxWidth={false} sx={{ maxWidth: 1500, pb: 7.5, px: { xs: 2, md: 4.75 } }}>
      <DashboardHeader isLive={isLive} username={username} />
      <Stack direction={{ xs: "column", md: "row" }} spacing={2.5} sx={{ py: 5, justifyContent: "space-between" }}>
        <Box>
          <Typography className="eyebrow">COMMAND CENTER · {new Date().toLocaleDateString("ru-RU")}</Typography>
          <Typography component="h1" variant="h4" sx={{ my: 1.25 }}>Добрый день, {username}.</Typography>
          <Typography color="text.secondary">Торговый контур работает в штатном режиме.</Typography>
        </Box>
        <Box sx={{ borderLeft: 1, borderColor: "primary.main", pl: 2.25, alignSelf: { md: "flex-end" } }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>РЕЖИМ ИСПОЛНЕНИЯ</Typography>
          <Typography variant="caption" color="primary.main" sx={{ fontWeight: 700 }}>PAPER</Typography>
        </Box>
      </Stack>
      <MetricsGrid portfolio={portfolio} />
      <Grid container spacing={1.5} sx={{ mt: 0 }}>
        <Grid size={{ xs: 12, lg: 8 }}><PositionsPanel positions={positions} /></Grid>
        <Grid size={{ xs: 12, lg: 4 }}><ServicesPanel services={services} /></Grid>
        <Grid size={{ xs: 12, lg: 8 }}><EventsPanel events={events} isLive={isLive} /></Grid>
        <Grid size={{ xs: 12, lg: 4 }}><SignalPanel /></Grid>
      </Grid>
    </Container>
  );
}
