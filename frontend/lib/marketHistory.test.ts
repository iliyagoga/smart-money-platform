import { beforeEach, expect, it, vi } from "vitest";
import { api } from "./api";
import { marketTimeframes, prepareMarketHistory, type MarketHistoryJob } from "./marketHistory";

vi.mock("./api", () => ({ api: vi.fn() }));

const activeJob = {
  id: "existing", symbol: "BTC-USDT-SWAP", timeframes: marketTimeframes, status: "RUNNING", progress: 20,
  ingested: 100, timeframe_status: {},
} satisfies MarketHistoryJob;

beforeEach(() => vi.clearAllMocks());

it("requests every market timeframe when viewing an asset without an active history job", async () => {
  const created = { ...activeJob, id: "new", status: "QUEUED" } satisfies MarketHistoryJob;
  vi.mocked(api).mockResolvedValue(created);

  await expect(prepareMarketHistory("ETH-USDT-SWAP", [{ ...activeJob, status: "COMPLETED" }])).resolves.toBe(created);

  expect(api).toHaveBeenCalledOnce();
  const [path, init] = vi.mocked(api).mock.calls[0];
  expect(path).toBe("/api/v1/exchange/exchange/history");
  expect(init?.method).toBe("POST");
  expect(JSON.parse(String(init?.body))).toMatchObject({
    symbol: "ETH-USDT-SWAP", timeframes: marketTimeframes, incremental: true, backfill: false,
  });
  expect(marketTimeframes).not.toContain("M1");
});

it("uses an existing job instead of starting a duplicate", async () => {
  await expect(prepareMarketHistory(activeJob.symbol, [activeJob])).resolves.toBe(activeJob);
  expect(api).not.toHaveBeenCalled();
});

it("starts a full history job when an existing job covers only one timeframe", async () => {
  const created = { ...activeJob, id: "full" };
  vi.mocked(api).mockResolvedValue(created);
  await expect(prepareMarketHistory(activeJob.symbol, [{ ...activeJob, timeframes: ["M15"] }])).resolves.toBe(created);
  expect(api).toHaveBeenCalledOnce();
});
