import { describe, expect, it } from "vitest";
import { isValidAssetSymbol, normalizeAssetSymbol } from "./useTradingAssets";

describe("trading asset symbols", () => {
  it("normalizes common separators", () => {
    expect(normalizeAssetSymbol(" sol/usdt_swap ")).toBe("SOL-USDT-SWAP");
  });

  it("validates spot and swap symbols", () => {
    expect(isValidAssetSymbol("ETH-USDT")).toBe(true);
    expect(isValidAssetSymbol("BTC-USDT-SWAP")).toBe(true);
    expect(isValidAssetSymbol("bad symbol")).toBe(false);
  });
});
