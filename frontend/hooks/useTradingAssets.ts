"use client";

import { useSyncExternalStore } from "react";

const storageKey = "smart-money-trading-assets";
const changeEvent = "smart-money-assets-change";
const defaultAssets = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"];
let cachedValue = "";
let cachedAssets = defaultAssets;

const readAssets = (): string[] => {
  const value = localStorage.getItem(storageKey) ?? JSON.stringify(defaultAssets);
  if (value === cachedValue) return cachedAssets;
  cachedValue = value;
  try {
    const parsed = JSON.parse(value) as unknown;
    cachedAssets = Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : defaultAssets;
  } catch {
    cachedAssets = defaultAssets;
  }
  return cachedAssets;
};

const subscribe = (listener: () => void) => {
  window.addEventListener("storage", listener);
  window.addEventListener(changeEvent, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(changeEvent, listener);
  };
};

const saveAssets = (assets: string[]) => {
  localStorage.setItem(storageKey, JSON.stringify(assets));
  window.dispatchEvent(new Event(changeEvent));
};

export function normalizeAssetSymbol(value: string): string {
  return value.trim().toUpperCase().replaceAll("/", "-").replaceAll("_", "-");
}

export function isValidAssetSymbol(value: string): boolean {
  return /^[A-Z0-9]{2,15}-[A-Z0-9]{2,10}(?:-SWAP)?$/.test(value);
}

export function useTradingAssets() {
  const assets = useSyncExternalStore(subscribe, readAssets, () => defaultAssets);
  return {
    assets,
    addAsset: (value: string) => {
      const symbol = normalizeAssetSymbol(value);
      if (!isValidAssetSymbol(symbol) || assets.includes(symbol)) return false;
      saveAssets([...assets, symbol]);
      return true;
    },
    removeAsset: (symbol: string) => saveAssets(assets.filter((asset) => asset !== symbol)),
  };
}
