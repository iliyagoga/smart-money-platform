"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";

export interface TradingAsset {
  symbol: string;
  display_name?: string;
  category: string;
  enabled: boolean;
  price_precision: number;
  quantity_precision: number;
  minimum_order_size: number;
  validation_status: string;
}

interface AssetsResponse { assets: TradingAsset[] }

const defaultAssets: TradingAsset[] = [
  {
    symbol: "BTC-USDT-SWAP", category: "crypto", enabled: true, price_precision: 2,
    quantity_precision: 6, minimum_order_size: .000001, validation_status: "ACTIVE",
  },
  {
    symbol: "ETH-USDT-SWAP", category: "crypto", enabled: true, price_precision: 2,
    quantity_precision: 6, minimum_order_size: .000001, validation_status: "ACTIVE",
  },
];

export function normalizeAssetSymbol(value: string): string {
  return value.trim().toUpperCase().replaceAll("/", "-").replaceAll("_", "-");
}

export function isValidAssetSymbol(value: string): boolean {
  return /^[A-Z0-9]{2,15}-[A-Z0-9]{2,10}(?:-SWAP)?$/.test(value);
}

export function useTradingAssets() {
  const [items, setItems] = useState<TradingAsset[]>(defaultAssets);
  const [error, setError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const reload = useCallback(() => setReloadKey((current) => current + 1), []);

  useEffect(() => {
    let active = true;
    api<AssetsResponse>("/api/v1/backtest/assets")
      .then((response) => { if (active) setItems(response.assets); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [reloadKey]);

  return {
    assets: items.map((asset) => asset.symbol),
    assetDetails: items,
    error,
    reload,
    addAsset: async (value: string) => {
      const symbol = normalizeAssetSymbol(value);
      if (!isValidAssetSymbol(symbol) || items.some((asset) => asset.symbol === symbol)) return false;
      await api("/api/v1/backtest/assets", {
        method: "POST",
        body: JSON.stringify({ symbol, category: "crypto" }),
      });
      reload();
      return true;
    },
    removeAsset: async (symbol: string) => {
      await api(`/api/v1/backtest/assets/${encodeURIComponent(symbol)}`, { method: "DELETE" });
      reload();
    },
  };
}
