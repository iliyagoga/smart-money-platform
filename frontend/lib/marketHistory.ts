import { api } from "./api";

export const marketTimeframes = ["M5", "M15", "M30", "H1", "H4", "D1"];

export interface MarketHistoryJob {
  id: string;
  symbol: string;
  timeframes: string[];
  status: "QUEUED" | "RUNNING" | "PAUSED" | "CANCELLED" | "COMPLETED" | "FAILED";
  progress: number;
  ingested: number;
  timeframe_status: Record<string, {
    status: MarketHistoryJob["status"];
    progress?: number;
    ingested: number;
    requests: number;
    error?: string;
  }>;
}

export async function prepareMarketHistory(symbol: string, jobs: MarketHistoryJob[]): Promise<MarketHistoryJob> {
  const running = jobs.find((job) => job.symbol === symbol && ["QUEUED", "RUNNING"].includes(job.status)
    && marketTimeframes.every((timeframe) => job.timeframes?.includes(timeframe)));
  if (running) return running;

  const now = Date.now();
  return api<MarketHistoryJob>("/api/v1/exchange/exchange/history", {
    method: "POST",
    body: JSON.stringify({
      symbol,
      timeframes: marketTimeframes,
      from_timestamp: now - 180 * 86_400_000,
      to_timestamp: now,
      incremental: true,
      backfill: false,
    }),
  });
}
