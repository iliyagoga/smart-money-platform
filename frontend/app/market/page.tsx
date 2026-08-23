"use client";

import { Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { AssetManager } from "../../components/backtest/AssetManager";
import { CandlestickChart } from "../../components/market/CandlestickChart";
import { EmptyState } from "../../components/ui/EmptyState";
import { SectionPage } from "../../components/layout/SectionPage";
import { useApiResource } from "../../hooks/useApiResource";
import { EventSocket } from "../../lib/socket";
import type { CandlesResponse, MarketStructure, PlatformEvent } from "../../lib/types";

const timeframes = ["M1", "M5", "M15", "H1", "H4"];

export default function MarketPage() {
  const [events, setEvents] = useState<PlatformEvent[]>([]);
  const [isLive, setIsLive] = useState(false);
  const [symbol, setSymbol] = useState("BTC-USDT-SWAP");
  const [timeframe, setTimeframe] = useState("M15");
  const query = `symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`;
  const candles = useApiResource<CandlesResponse>(`/api/v1/data/market/candles?${query}&limit=200`);
  const structure = useApiResource<MarketStructure>(`/api/v1/smc/smart-money/structure?${query}`);

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
    <SectionPage
      title="Рынок"
      description="Свечной график, зоны Smart Money и события рынка в реальном времени."
      error={candles.error || structure.error}
      isLoading={candles.isLoading || structure.isLoading}
      onReload={() => { candles.reload(); structure.reload(); }}
    >
      <AssetManager selectedAsset={symbol} onSelect={setSymbol} />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 2 }}>
        <TextField
          select
          label="Таймфрейм"
          value={timeframe}
          onChange={(event) => setTimeframe(event.target.value)}
          size="small"
          sx={{ minWidth: 140 }}
        >
          {timeframes.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </TextField>
        <Chip label={isLive ? "Поток подключён" : "Подключение…"} color={isLive ? "success" : "default"} variant="outlined" />
      </Stack>
      <CandlestickChart candles={candles.data?.candles ?? []} structure={structure.data} />
      <Typography variant="h5" sx={{ mt: 4, mb: 2 }}>Лента событий</Typography>
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
