import type { BacktestSettings } from "./types";

type JsonObject = Record<string, unknown>;

export function readSettingsConfig(value: unknown): Partial<BacktestSettings> {
  if (!isObject(value)) throw new Error("В буфере обмена нет конфигурации");
  const request = isObject(value.request) ? value.request : undefined;
  const wrapped = request && isObject(request.config) ? request.config
    : isObject(value.config) ? value.config : value;
  const normalized = snakeToCamel(wrapped) as Partial<BacktestSettings>;
  if (!isObject(normalized.elliott) || (normalized.strategy && normalized.strategy !== "ELLIOTT")) {
    throw new Error("В буфере обмена нет Elliott-конфигурации");
  }
  return normalized;
}

export function mergeSettingsConfig(current: BacktestSettings, value: unknown): BacktestSettings {
  const normalized = readSettingsConfig(value);
  return {
    ...current,
    ...normalized,
    strategy: "ELLIOTT",
    elliott: { ...current.elliott, ...normalized.elliott },
  };
}

function snakeToCamel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(snakeToCamel);
  if (!isObject(value)) return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()), snakeToCamel(item),
  ]));
}

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
