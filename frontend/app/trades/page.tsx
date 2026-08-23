"use client";

import { SectionPage } from "../../components/layout/SectionPage";
import { PositionsPanel } from "../../components/dashboard/PositionsPanel";
import { useApiResource } from "../../hooks/useApiResource";
import type { Position, PositionsResponse } from "../../lib/types";

export default function TradesPage() {
  const resource = useApiResource<PositionsResponse | Position[]>("/api/v1/execution/positions");
  const positions = Array.isArray(resource.data) ? resource.data : (resource.data?.positions ?? []);
  return <SectionPage title="Сделки" description="Открытые позиции и состояние исполнения." {...resource} onReload={resource.reload}>
    <PositionsPanel positions={positions} />
  </SectionPage>;
}
