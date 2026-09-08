"use client";

import { Alert, Box, Button, Container, Grid, Stack, Typography } from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { EventSocket } from "../lib/socket";
import type { PlatformEvent, Portfolio, Position, PositionsResponse, ServiceStatus, ServicesResponse } from "../lib/types";
import { DashboardHeader } from "./dashboard/DashboardHeader";
import { useAuth } from "./auth/AuthProvider";
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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const { username } = useAuth();

  const loadDashboard = useCallback(async () => {
    setIsRefreshing(true);
    setLoadError("");
    try {
      const [portfolioData, servicesData, positionsData] = await Promise.all([
        api<Portfolio>("/api/v1/analytics/portfolio"),
        api<ServicesResponse>("/api/v1/analytics/monitoring/services"),
        api<PositionsResponse | Position[]>("/api/v1/execution/positions"),
      ]);
      setPortfolio(portfolioData);
      setServices(servicesData.services ?? []);
      setPositions(Array.isArray(positionsData) ? positionsData : (positionsData.positions ?? []));
    } catch (reason) {
      setLoadError(reason instanceof Error ? reason.message : "Не удалось загрузить данные");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
    // На обзорной странице нужны только события, требующие внимания. Рыночный
    // поток candle/trade/orderbook остаётся на странице «Рынок».
    const socket = new EventSocket(["scenario.*", "position.*"]);
    socket.subscribeStatus(setIsLive);
    socket.subscribe((event) => {
      setEvents((currentEvents) => [event, ...currentEvents].slice(0, 8));
      if (event.event_type.startsWith("position.")) void loadDashboard();
    });
    void socket.connect();
    return () => socket.close();
  }, [loadDashboard]);

  return (
    <Container component="main" maxWidth={false} sx={{ width: "100%", pb: 7.5, px: { xs: 2, md: 3, xl: 4 } }}>
      <DashboardHeader isLive={isLive} username={username} />
      <Stack id="overview" direction={{ xs: "column", md: "row" }} spacing={2.5} sx={{ py: { xs: 4, md: 6 }, justifyContent: "space-between" }}>
        <Box>
          <Typography className="eyebrow">COMMAND CENTER · {new Date().toLocaleDateString("ru-RU")}</Typography>
          <Typography component="h1" variant="h3" sx={{ my: 1.25, fontSize: { xs: 32, md: 44 } }}>Добрый день, {username}.</Typography>
          <Typography color="text.secondary">Торговый контур работает в штатном режиме.</Typography>
        </Box>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", alignSelf: { md: "flex-end" } }}>
          <Box sx={{ borderLeft: 2, borderColor: "primary.main", pl: 2.25 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>РЕЖИМ ИСПОЛНЕНИЯ</Typography>
            <Typography variant="caption" color="primary.main" sx={{ fontWeight: 700 }}>PAPER</Typography>
          </Box>
          <Button variant="outlined" onClick={() => void loadDashboard()} disabled={isRefreshing}>
            {isRefreshing ? "Обновляем…" : "↻ Обновить"}
          </Button>
        </Stack>
      </Stack>
      {loadError && <Alert severity="error" sx={{ mb: 2 }}>{loadError}</Alert>}
      <MetricsGrid portfolio={portfolio} />
      <Grid container spacing={1.5} sx={{ mt: 0 }}>
        <Grid id="positions" size={{ xs: 12, lg: 8 }} sx={{ scrollMarginTop: 92 }}><PositionsPanel positions={positions} /></Grid>
        <Grid id="services" size={{ xs: 12, lg: 4 }} sx={{ scrollMarginTop: 92 }}><ServicesPanel services={services} /></Grid>
        <Grid id="events" size={{ xs: 12, lg: 8 }} sx={{ scrollMarginTop: 92 }}><EventsPanel events={events} isLive={isLive} /></Grid>
        <Grid id="insights" size={{ xs: 12, lg: 4 }} sx={{ scrollMarginTop: 92 }}><SignalPanel /></Grid>
      </Grid>
    </Container>
  );
}
