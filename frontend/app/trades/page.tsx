"use client";

import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { SectionPage } from "../../components/layout/SectionPage";
import { PositionsPanel } from "../../components/dashboard/PositionsPanel";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import type { Position, PositionsResponse } from "../../lib/types";

export default function TradesPage() {
  const resource = useApiResource<PositionsResponse | Position[]>("/api/v1/execution/positions");
  const { roles } = useAuth();
  const [actionError, setActionError] = useState("");
  const [closingId, setClosingId] = useState("");
  const positions = Array.isArray(resource.data) ? resource.data : (resource.data?.positions ?? []);
  const canClose = roles.some((role) => role === "trader" || role === "admin");

  const closePosition = async (position: Position) => {
    setClosingId(position.id);
    setActionError("");
    try {
      await api(`/api/v1/execution/positions/${position.id}/close`, {
        method: "POST",
        body: JSON.stringify({ reason: "MANUAL" }),
      });
      resource.reload();
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setClosingId("");
    }
  };

  return <SectionPage title="Сделки" description="Открытые позиции и состояние исполнения." {...resource} error={actionError || resource.error} onReload={resource.reload}>
    <PositionsPanel positions={positions} canClose={canClose} closingId={closingId} onClose={(position) => void closePosition(position)} />
  </SectionPage>;
}
