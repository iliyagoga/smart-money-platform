"use client";

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Grid, Snackbar, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { PositionsPanel } from "../../components/dashboard/PositionsPanel";
import { SectionPage } from "../../components/layout/SectionPage";
import { OrderTicket } from "../../components/trades/OrderTicket";
import { TradeHistory } from "../../components/trades/TradeHistory";
import { TradeStatisticsGrid } from "../../components/trades/TradeStatisticsGrid";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { OrderDraft, Position, PositionsResponse, TradeStatistics, TradesResponse } from "../../lib/types";

export default function TradesPage() {
  const positionsResource = useApiResource<PositionsResponse | Position[]>("/api/v1/execution/positions");
  const historyResource = useApiResource<TradesResponse>("/api/v1/execution/trades/history?limit=100");
  const statisticsResource = useApiResource<TradeStatistics>("/api/v1/execution/trades/statistics");
  const { roles } = useAuth();
  const [actionError, setActionError] = useState("");
  const [closingPosition, setClosingPosition] = useState<Position>();
  const [isClosing, setIsClosing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const positions = Array.isArray(positionsResource.data)
    ? positionsResource.data
    : (positionsResource.data?.positions ?? []);
  const canTrade = roles.some((role) => role === "trader" || role === "admin");

  const reloadTradingData = () => {
    positionsResource.reload();
    historyResource.reload();
    statisticsResource.reload();
  };

  const createOrder = async (order: OrderDraft) => {
    setIsSubmitting(true);
    setActionError("");
    try {
      await api("/api/v1/execution/orders", { method: "POST", body: JSON.stringify(order) });
      setSuccessMessage("Ордер успешно отправлен в paper-контур");
      reloadTradingData();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsSubmitting(false);
    }
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

  const errors = actionError || positionsResource.error || historyResource.error || statisticsResource.error;

  return (
    <SectionPage
      title="Сделки"
      description="Paper-ордера, открытые позиции и статистика исполнения."
      error={errors}
      isLoading={positionsResource.isLoading}
      onReload={reloadTradingData}
    >
      <TradeStatisticsGrid statistics={statisticsResource.data} />
      <Grid container spacing={1.5} sx={{ mt: 0 }}>
        <Grid size={{ xs: 12, xl: 8 }}>
          <PositionsPanel positions={positions} canClose={canTrade} onClose={setClosingPosition} />
        </Grid>
        <Grid size={{ xs: 12, xl: 4 }}>
          <OrderTicket canTrade={canTrade} isSubmitting={isSubmitting} onSubmit={(order) => void createOrder(order)} />
        </Grid>
      </Grid>
      <TradeHistory trades={historyResource.data?.trades ?? []} />
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
