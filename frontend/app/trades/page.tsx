"use client";

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, FormControl, Grid, InputLabel, MenuItem, Select, Snackbar, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { PositionsPanel } from "../../components/dashboard/PositionsPanel";
import { SectionPage } from "../../components/layout/SectionPage";
import { TradeHistory } from "../../components/trades/TradeHistory";
import { TradeStatisticsGrid } from "../../components/trades/TradeStatisticsGrid";
import { TradeAnalyzer } from "../../components/trades/TradeAnalyzer";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { Position, PositionsResponse, TradeAnalysisResponse, TradeAssetsResponse, TradeStatistics, TradesResponse } from "../../lib/types";

export default function TradesPage() {
  const [symbol, setSymbol] = useState("");
  const symbolQuery = symbol ? `?symbol=${encodeURIComponent(symbol)}&limit=1000` : "?limit=1000";
  const positionsResource = useApiResource<PositionsResponse | Position[]>("/api/v1/execution/positions");
  const assetsResource = useApiResource<TradeAssetsResponse>("/api/v1/execution/trades/assets");
  const historyResource = useApiResource<TradesResponse>(`/api/v1/execution/trades/history${symbolQuery}`);
  const statisticsResource = useApiResource<TradeStatistics>(`/api/v1/execution/trades/statistics${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`);
  const analysisResource = useApiResource<TradeAnalysisResponse>(`/api/v1/execution/trades/analysis${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`);
  const { roles } = useAuth();
  const [actionError, setActionError] = useState("");
  const [closingPosition, setClosingPosition] = useState<Position>();
  const [isClosing, setIsClosing] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const positions = Array.isArray(positionsResource.data)
    ? positionsResource.data
    : (positionsResource.data?.positions ?? []);
  const canTrade = roles.some((role) => role === "trader" || role === "admin");
  const symbols = Array.from(new Set([
    ...(assetsResource.data?.assets.map((asset) => asset.symbol) ?? []), ...positions.map((position) => position.symbol),
  ])).sort();

  const reloadTradingData = () => {
    positionsResource.reload();
    historyResource.reload();
    statisticsResource.reload();
    analysisResource.reload();
    assetsResource.reload();
  };

  const closePosition = async () => {
    if (!closingPosition) return;
    setIsClosing(true);
    setActionError("");
    try {
      await api(`/api/v1/execution/positions/${closingPosition.id}/close`, {
        method: "POST",
        body: JSON.stringify({ reason: "MANUAL" }),
      });
      setSuccessMessage(`Позиция ${closingPosition.symbol} закрыта`);
      setClosingPosition(undefined);
      reloadTradingData();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsClosing(false);
    }
  };

  const errors = actionError || positionsResource.error || assetsResource.error || historyResource.error
    || statisticsResource.error || analysisResource.error;

  return (
    <SectionPage
      title="Сделки"
      description="Позиции, сделки и аналитика торговой системы Elliott."
      error={errors}
      isLoading={positionsResource.isLoading}
      onReload={reloadTradingData}
    >
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 1.5, justifyContent: "space-between", alignItems: { sm: "center" } }}>
        <Typography variant="body2" color="text.secondary">Показаны {symbol ? `сделки по ${symbol}` : "сделки по всем активам"}</Typography>
        <FormControl size="small" sx={{ minWidth: 220 }}><InputLabel>Актив</InputLabel><Select value={symbol} label="Актив" onChange={(event) => setSymbol(event.target.value)}>
          <MenuItem value="">Все активы</MenuItem>{symbols.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
        </Select></FormControl>
      </Stack>
      <TradeStatisticsGrid statistics={statisticsResource.data} />
      <Grid container spacing={1.5} sx={{ mt: 0 }}>
        <Grid size={{ xs: 12 }}>
          <PositionsPanel positions={positions} canClose={canTrade} onClose={setClosingPosition} />
        </Grid>
      </Grid>
      <TradeHistory trades={historyResource.data?.trades ?? []} />
      <TradeAnalyzer analysis={analysisResource.data} />
      <Dialog open={Boolean(closingPosition)} onClose={() => setClosingPosition(undefined)}>
        <DialogTitle>Закрыть позицию?</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography>Позиция {closingPosition?.symbol} будет закрыта по текущей цене.</Typography>
            <Typography color="text.secondary" variant="body2">Операция попадёт в историю и повлияет на PnL.</Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClosingPosition(undefined)}>Отмена</Button>
          <Button color="error" variant="contained" onClick={() => void closePosition()} disabled={isClosing}>
            {isClosing ? "Закрываем…" : "Закрыть позицию"}
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={Boolean(successMessage)} autoHideDuration={4500} onClose={() => setSuccessMessage("")} message={successMessage} />
    </SectionPage>
  );
}
