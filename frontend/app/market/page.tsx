"use client";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { TradingViewChart, type LiveElliottPattern, type LiveEntryScenario } from "../../components/market/TradingViewChart";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import { EventSocket } from "../../lib/socket";
import { defaultBacktestSettings } from "../../lib/backtest/defaultSettings";
import type { BacktestSettings } from "../../lib/backtest/types";
import type { Candle, CandlesResponse } from "../../lib/types";

const allTimeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
type TradingConfig = { symbol: string; mode: string; status: string; config?: BacktestSettings | string };
type TradingConfigsResponse = { configs: TradingConfig[] };
type ElliottPatternsResponse = { symbol: string; patterns: LiveElliottPattern[]; total: number };
type LiveEntriesResponse = { symbol: string; entries: LiveEntryScenario[]; total: number };
type ElliottHistoryResponse = {
  symbol: string; patterns: LiveElliottPattern[]; entries: LiveEntryScenario[];
  patterns_total: number; entries_total: number;
};
export default function MarketPage() {
  const assets = useTradingAssets(); const [symbol, setSymbol] = useState("");
  const [viewSymbol, setViewSymbol] = useState("");
  const [settings, setSettings] = useState<BacktestSettings>(() => ({ ...defaultBacktestSettings, elliott: { ...defaultBacktestSettings.elliott } }));
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [selectedTf, setSelectedTf] = useState("M15");
  const tradingConfigs = useApiResource<TradingConfigsResponse>("/api/v1/execution/trading-configs");
  const activeConfigs = useMemo(() => (tradingConfigs.data?.configs ?? []).filter((config) => config.status === "ACTIVE"), [tradingConfigs.data]);
  const activeAssets = useMemo(() => activeConfigs.map((config) => config.symbol), [activeConfigs]);
  const selected = symbol || assets.assets[0] || "";
  const viewed = viewSymbol || activeAssets[0] || "";
  const availableTimeframes = allTimeframes;
  const selectedConfig = activeConfigs.find((config) => config.symbol === viewed);
  const macroTimeframe = tradingMacroTimeframe(selectedConfig?.config);
  const strategyTimeframes = tradingElliottTimeframes(selectedConfig?.config);
  const candleLimit = timeframeWindowLimit(selectedTf, macroTimeframe);
  const candles = useOkxCandles(viewed, selectedTf, candleLimit);
  const elliottPatterns = useApiResource<ElliottPatternsResponse>(`/api/v1/smc/elliott/patterns?symbol=${encodeURIComponent(viewed)}`);
  const liveEntries = useApiResource<LiveEntriesResponse>(`/api/v1/smc/elliott/entries?symbol=${encodeURIComponent(viewed)}`);
  const historicalEntryCandles = useOkxCandles(viewed,strategyTimeframes.entry,
    timeframeWindowLimit(strategyTimeframes.entry,strategyTimeframes.macro));
  const historicalStructureCandles = useOkxCandles(viewed,strategyTimeframes.structure,
    timeframeWindowLimit(strategyTimeframes.structure,strategyTimeframes.macro));
  const historicalMacroCandles = useOkxCandles(viewed,strategyTimeframes.macro,500);
  const [historicalElliott,setHistoricalElliott] = useState<ElliottHistoryResponse | null>(null);
  useEffect(() => {
    if (!viewed || historicalEntryCandles.loading || historicalStructureCandles.loading || historicalMacroCandles.loading) return;
    const byTimeframe = {
      [strategyTimeframes.entry]: historicalEntryCandles.data.candles,
      [strategyTimeframes.structure]: historicalStructureCandles.data.candles,
      [strategyTimeframes.macro]: historicalMacroCandles.data.candles,
    };
    if (Object.values(byTimeframe).some((items) => !items.length)) return;
    let cancelled=false;
    void api<ElliottHistoryResponse>("/api/v1/smc/elliott/history",{ method:"POST",
      body:JSON.stringify({ symbol:viewed,candles_by_timeframe:byTimeframe }) })
      .then((result) => { if (!cancelled) setHistoricalElliott(result); })
      .catch(() => { if (!cancelled) setHistoricalElliott(null); });
    return () => { cancelled=true; };
  },[viewed,strategyTimeframes.entry,strategyTimeframes.structure,strategyTimeframes.macro,
    historicalEntryCandles.loading,historicalStructureCandles.loading,historicalMacroCandles.loading,
    historicalEntryCandles.data.candles,historicalStructureCandles.data.candles,historicalMacroCandles.data.candles]);
  const reloadCandles = candles.reload;
  useEffect(() => {
    if (!symbol && assets.assets.length) setSymbol(assets.assets[0]);
    if (!viewSymbol && activeAssets.length) setViewSymbol(activeAssets[0]);
  }, [assets.assets, activeAssets, symbol, viewSymbol]);
  const reloadPatterns = elliottPatterns.reload;
  const reloadScenarios = liveEntries.reload;
  useEffect(() => { const socket = new EventSocket(["candle.*","scenario.*"]); const unsubscribe = socket.subscribe((event) => { if (event.payload?.symbol === viewed) { if (!event.payload.timeframe || event.payload.timeframe === selectedTf) reloadCandles(); reloadPatterns(); reloadScenarios(); } }); void socket.connect(); const timer = window.setInterval(() => { reloadCandles(); reloadPatterns(); reloadScenarios(); }, 15_000); return () => { unsubscribe(); socket.close(); window.clearInterval(timer); }; }, [viewed, selectedTf, reloadCandles, reloadPatterns, reloadScenarios]);
  const save = async () => { setSaving(true); setMessage(""); try { if (!selected) throw new Error("Введите актив"); const elliottTimeframes = [settings.elliott.entryTimeframe, settings.elliott.structureTimeframe, settings.elliott.macroTimeframe]; const dataset = await api<{ timeframes: Array<{ timeframe: string; candles: number }> }>(`/api/v1/backtest/datasets/${encodeURIComponent(selected)}`).catch(() => ({ timeframes: [] })); const missing = elliottTimeframes.filter((timeframe) => !dataset.timeframes.some((item) => item.timeframe === timeframe && item.candles > 0)); if (missing.length) { await api("/api/v1/exchange/exchange/history", { method: "POST", body: JSON.stringify({ symbol: selected, timeframes: missing, from_timestamp: Date.now() - 180 * 86400000, to_timestamp: Date.now(), incremental: false, backfill: false }) }); setMessage(`Для ${selected} запрошены свечи: ${missing.join(", ")}. Конфигурация сохраняется.`); } await api(`/api/v1/backtest/assets`, { method: "POST", body: JSON.stringify({ symbol: selected, category: "crypto" }) }).catch((error: unknown) => { if (!(error instanceof Error) || !error.message.startsWith("409")) throw error; }); await api("/api/v1/execution/trading-configs", { method: "POST", body: JSON.stringify({ symbol: selected, mode: "SIMULATION", config: settings }) }); await api("/api/v1/exchange/exchange/reload-symbols", { method: "POST" }).catch(() => undefined); assets.reload(); tradingConfigs.reload(); setMessage(`Актив ${selected} зарегистрирован в автономной симуляции.`); } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); } finally { setSaving(false); } };
  const removeLiveAsset = async () => {
    if (!viewed || !window.confirm(`Удалить ${viewed} из live trading?`)) return;
    setSaving(true); setMessage("");
    try {
      await api(`/api/v1/execution/trading-configs/${encodeURIComponent(viewed)}`, { method: "DELETE" });
      const remaining = activeAssets.filter((item) => item !== viewed);
      setViewSymbol(remaining[0] ?? "");
      tradingConfigs.reload();
      setMessage(`Актив ${viewed} удалён из live trading.`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  const pasteConfig = async () => {
    try {
      const parsed = JSON.parse(await navigator.clipboard.readText()) as { symbol?: string; config?: Record<string, unknown> };
      if (!parsed.config || typeof parsed.config !== "object") throw new Error("В буфере нет конфигурации бэктеста");
      const normalized = snakeToCamel(parsed.config) as Partial<BacktestSettings>;
      setSettings((current) => ({ ...current, ...normalized, strategy: "ELLIOTT", elliott: { ...current.elliott, ...(normalized.elliott as Partial<BacktestSettings["elliott"]> ?? {}) } }));
      if (parsed.symbol) setSymbol(parsed.symbol);
      setMessage("Конфигурация вставлена из буфера обмена.");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
  };
  return <SectionPage title="Рынок" description="Регистрация Elliott-активов и отдельный просмотр их состояния."><Stack spacing={2}>
    <Accordion defaultExpanded disableGutters sx={{ width: "100%", border: 1, borderColor: "divider", "&:before": { display: "none" } }}>
      <AccordionSummary expandIcon={<Typography component="span" sx={{ fontSize: 22 }}>⌄</Typography>}><Typography variant="h6">Регистрация торгового актива</Typography></AccordionSummary>
      <AccordionDetails><Stack spacing={2}><TextField fullWidth label="Актив" placeholder="BTC-USDT-SWAP" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} /><Alert severity="info">Параметры ниже полностью совпадают с Elliott-настройками бэктеста и сохраняются в конфигурации автоторговли.</Alert><BacktestSettingsForm isRunning={saving} onChange={setSettings} onRun={() => void save()} progress={0} settings={settings} templates={[]} elliottOnly submitLabel="Зарегистрировать актив" /><Button variant="outlined" onClick={() => void pasteConfig()} disabled={saving}>Вставить скопированную конфигурацию</Button></Stack></AccordionDetails>
    </Accordion>
    {message && <Alert severity={message.includes("зарегистрирован") || message.includes("вставлена") || message.includes("удалён") ? "success" : "error"}>{message}</Alert>}
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, width: "100%" }}><Stack spacing={1.5}><Typography variant="h6">Состояние актива</Typography><Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><TextField fullWidth select label="Актив для просмотра" value={viewed} onChange={(e) => { setHistoricalElliott(null); setViewSymbol(e.target.value); }}>{activeAssets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><TextField fullWidth select label="Просматриваемый таймфрейм" value={selectedTf} onChange={(e) => setSelectedTf(e.target.value)} disabled={!availableTimeframes.length}>{availableTimeframes.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><Button color="error" variant="contained" disabled={!viewed || saving} onClick={() => void removeLiveAsset()} sx={{ minWidth: 190, alignSelf: "center", borderRadius: 1, px: 2.5, py: .5, boxShadow: "none", textTransform: "none", fontWeight: 700, "&:hover": { boxShadow: "0 4px 12px rgba(211,47,47,.2)" } }}>Удалить актив</Button></Stack>{viewed ? <TradingViewChart candles={candles.data?.candles ?? []} elliottPatterns={historicalElliott?.patterns ?? elliottPatterns.data?.patterns ?? []} entryScenarios={historicalElliott?.entries ?? liveEntries.data?.entries ?? []} /> : <Typography color="text.secondary">Нет активных активов для просмотра.</Typography>}</Stack></Paper>
  </Stack></SectionPage>;
}

function snakeToCamel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(snakeToCamel);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()), snakeToCamel(item),
  ]));
}

const timeframeMinutes: Record<string, number> = {
  M1: 1, M5: 5, M15: 15, M30: 30, H1: 60, H4: 240, D1: 1440,
};

function tradingMacroTimeframe(value?: BacktestSettings | string): string {
  if (!value) return "H4";
  try {
    const config = typeof value === "string" ? JSON.parse(value) as Record<string, unknown> : value;
    const elliott = (config as { elliott?: Record<string, unknown> }).elliott;
    const timeframe = elliott?.macroTimeframe ?? elliott?.macro_timeframe;
    return typeof timeframe === "string" && timeframe in timeframeMinutes ? timeframe : "H4";
  } catch { return "H4"; }
}

function tradingElliottTimeframes(value?: BacktestSettings | string) {
  const fallback={ entry:"M15",structure:"H1",macro:"H4" };
  if (!value) return fallback;
  try {
    const config=typeof value === "string" ? JSON.parse(value) as Record<string,unknown> : value;
    const elliott=(config as { elliott?:Record<string,unknown> }).elliott;
    const pick=(camel:string,snake:string,defaultValue:string) => {
      const item=elliott?.[camel] ?? elliott?.[snake];
      return typeof item === "string" && item in timeframeMinutes ? item : defaultValue;
    };
    return { entry:pick("entryTimeframe","entry_timeframe",fallback.entry),
      structure:pick("structureTimeframe","structure_timeframe",fallback.structure),
      macro:pick("macroTimeframe","macro_timeframe",fallback.macro) };
  } catch { return fallback; }
}

function timeframeWindowLimit(selected: string, macro: string): number {
  const selectedMinutes = timeframeMinutes[selected] ?? 15;
  const macroMinutes = timeframeMinutes[macro] ?? 240;
  return Math.min(200_000, Math.max(500, Math.ceil(500 * macroMinutes / selectedMinutes)));
}

const candleCache = new Map<string, Candle[]>();

function mergeCandles(current: Candle[], incoming: Candle[]): Candle[] {
  return [...new Map([...current, ...incoming].map((item) => [item.timestamp, item])).values()]
    .sort((left, right) => left.timestamp - right.timestamp);
}

function useOkxCandles(symbol: string, timeframe: string, limit: number) {
  const key = `${symbol}:${timeframe}`;
  const [data, setData] = useState<CandlesResponse>({ symbol, timeframe, candles: candleCache.get(key) ?? [] });
  const [reloadKey, setReloadKey] = useState(0);
  const [loading,setLoading] = useState(false);
  const cacheRef = useRef(candleCache);
  const reload = useCallback(() => setReloadKey((current) => current + 1), []);

  useEffect(() => {
    let cancelled = false;
    if (!symbol) { setData({ symbol, timeframe, candles: [] }); return () => { cancelled = true; }; }
    const load = async () => {
      setLoading(true);
      try {
      let collected = cacheRef.current.get(key) ?? [];
      const first = await api<CandlesResponse>(
        `/api/v1/exchange/exchange/market-candles?symbol=${encodeURIComponent(symbol)}`
        + `&timeframe=${timeframe}&limit=${Math.min(300,limit)}`,
      );
      collected = mergeCandles(collected,first.candles);
      if (!cancelled) setData({ symbol, timeframe, candles: collected.slice(-limit) });
      let cursor = collected[0]?.timestamp;
      while (!cancelled && collected.length < limit && first.candles.length) {
        const remaining = Math.min(300,limit-collected.length);
        const page = await api<CandlesResponse>(
          `/api/v1/exchange/exchange/market-candles?symbol=${encodeURIComponent(symbol)}`
          + `&timeframe=${timeframe}&limit=${remaining}&after=${cursor}`,
        );
        if (!page.candles.length) break;
        const previousSize = collected.length;
        collected = mergeCandles(collected,page.candles);
        const nextCursor = collected[0]?.timestamp;
        if (collected.length === previousSize || nextCursor === cursor) break;
        cursor = nextCursor;
        cacheRef.current.set(key,collected);
        if (!cancelled) setData({ symbol, timeframe, candles: collected.slice(-limit) });
        if (page.candles.length < remaining) break;
      }
      const result = collected.slice(-limit);
      cacheRef.current.set(key,result);
      if (!cancelled) setData({ symbol, timeframe, candles: result });
      } finally { if (!cancelled) setLoading(false); }
    };
    void load().catch(() => { if (!cancelled) setData({ symbol, timeframe, candles: cacheRef.current.get(key) ?? [] }); });
    return () => { cancelled = true; };
  }, [key, limit, reloadKey, symbol, timeframe]);

  return { data, reload, loading };
}
