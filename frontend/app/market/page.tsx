"use client";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { EmptyState } from "../../components/ui/EmptyState";
import { TradingViewChart, type LiveElliottPattern, type LiveEntryScenario } from "../../components/market/TradingViewChart";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import { EventSocket } from "../../lib/socket";
import { defaultBacktestSettings } from "../../lib/backtest/defaultSettings";
import type { BacktestSettings } from "../../lib/backtest/types";
import { mergeSettingsConfig } from "../../lib/backtest/configClipboard";
import type { Candle, CandlesResponse } from "../../lib/types";

const allTimeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
type TradingMode = "PAPER" | "DEMO" | "PRODUCTION";
type TradingConfig = { symbol: string; mode: TradingMode; status: string; config?: BacktestSettings | string };
type TradingConfigsResponse = { configs: TradingConfig[] };
type ElliottPatternsResponse = { symbol: string; patterns: LiveElliottPattern[]; total: number };
type LiveEntriesResponse = { symbol: string; entries: LiveEntryScenario[]; total: number };
type ElliottHistoryResponse = {
  symbol: string; status: "NOT_BUILT" | "BUILDING" | "WAITING_FOR_DATA" | "COMPLETED" | "FAILED";
  error?: string; message?: string; updated_at?: number;
  patterns: LiveElliottPattern[]; entries: LiveEntryScenario[]; trades: HistoricalPaperTrade[];
};
type HistoricalPaperTrade = {
  id: string; direction: "LONG" | "SHORT"; entry_time: number; entry_price: number;
  exit_time: number; exit_price: number; pnl: number; pnl_percent: number; reason: string;
  initial_stop?: number; take_profit_prices?: number[]; signal_timeframe?: string;
};
export default function MarketPage() {
  const assets = useTradingAssets(); const [symbol, setSymbol] = useState("");
  const [viewSymbol, setViewSymbol] = useState("");
  const [tradingMode, setTradingMode] = useState<TradingMode>("PAPER");
  const [settings, setSettings] = useState<BacktestSettings>(() => ({ ...defaultBacktestSettings, elliott: { ...defaultBacktestSettings.elliott } }));
  const [editingSymbol,setEditingSymbol]=useState("");
  const [editingInitialCapital,setEditingInitialCapital]=useState<number>();
  const [suppressedActiveAssets,setSuppressedActiveAssets]=useState<Set<string>>(()=>new Set());
  const [settingsExpanded,setSettingsExpanded]=useState(false);
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState(""); const [selectedTf, setSelectedTf] = useState("M15");
  const tradingConfigs = useApiResource<TradingConfigsResponse>("/api/v1/execution/trading-configs");
  const serverActiveConfigs = useMemo(() => (tradingConfigs.data?.configs ?? []).filter((config) => config.status === "ACTIVE"), [tradingConfigs.data]);
  const activeConfigs = useMemo(
    () => serverActiveConfigs.filter((config) => !suppressedActiveAssets.has(config.symbol)),
    [serverActiveConfigs,suppressedActiveAssets],
  );
  const activeAssets = useMemo(() => activeConfigs.map((config) => config.symbol), [activeConfigs]);
  const selected = symbol || assets.assets[0] || "";
  const viewed = viewSymbol || activeAssets[0] || "";
  const availableTimeframes = allTimeframes;
  const selectedConfig = activeConfigs.find((config) => config.symbol === viewed);
  const isEditing=editingSymbol===selected;
  const macroTimeframe = tradingMacroTimeframe(selectedConfig?.config);
  const candleLimit = Math.min(10_000,timeframeWindowLimit(selectedTf, macroTimeframe));
  const elliottPatterns = useApiResource<ElliottPatternsResponse>(`/api/v1/elliott/elliott/patterns?symbol=${encodeURIComponent(viewed)}`);
  const liveEntries = useApiResource<LiveEntriesResponse>(`/api/v1/elliott/elliott/entries?symbol=${encodeURIComponent(viewed)}`);
  const historicalElliott = useApiResource<ElliottHistoryResponse>(`/api/v1/elliott/elliott/history?symbol=${encodeURIComponent(viewed)}`);
  const candles = useMarketCandles(viewed,selectedTf,candleLimit);
  const currentHistory = historicalElliott.data?.symbol === viewed ? historicalElliott.data : undefined;
  const displayedPatterns = currentHistory?.status === "COMPLETED"
    ? currentHistory.patterns : (elliottPatterns.data?.symbol === viewed ? elliottPatterns.data.patterns : []);
  const displayedEntries = useMemo(() => [...new Map([
    ...(currentHistory?.entries ?? []),...(liveEntries.data?.symbol === viewed ? liveEntries.data.entries : []),
  ].map((item) => [item.id,item])).values()], [currentHistory?.entries,liveEntries.data,viewed]);
  const reloadCandles = candles.reload;
  const applyLiveCandle = candles.applyLiveCandle;
  useEffect(() => {
    if (!symbol && assets.assets.length) setSymbol(assets.assets[0]);
    setViewSymbol((current) => current && activeAssets.includes(current) ? current : activeAssets[0] ?? "");
  }, [assets.assets, activeAssets, symbol]);
  useEffect(() => {
    const serverSymbols=new Set(serverActiveConfigs.map((config)=>config.symbol));
    setSuppressedActiveAssets((current) => {
      const next=new Set([...current].filter((item)=>serverSymbols.has(item)));
      return next.size===current.size ? current : next;
    });
  },[serverActiveConfigs]);
  const reloadPatterns = elliottPatterns.reload;
  const reloadScenarios = liveEntries.reload;
  const reloadHistory = historicalElliott.reload;
  const reloadTradingConfigs=tradingConfigs.reload;
  useEffect(() => {
    if (!viewed)return;
    const marketSocket=new EventSocket(["candle.*","scenario.*"],[viewed]);
    const unsubscribeMarket=marketSocket.subscribe((event) => {
      if (event.payload?.symbol!==viewed)return;
      if (event.event_type.startsWith("candle.") && event.payload.timeframe===selectedTf) {
        const { timestamp,open,high,low,close,volume }=event.payload;
        if ([timestamp,open,high,low,close,volume].every((value)=>typeof value==="number"))
          applyLiveCandle({ timestamp:timestamp!,open:open!,high:high!,low:low!,close:close!,volume:volume! });
      }
      if (event.event_type.startsWith("scenario.")) { reloadPatterns();reloadScenarios(); }
    });
    const configSocket=new EventSocket(["trading.config.*"]);
    const unsubscribeConfig=configSocket.subscribe(()=>reloadTradingConfigs());
    void marketSocket.connect();void configSocket.connect();
    const timer=window.setInterval(() => { reloadCandles();reloadPatterns();reloadScenarios();reloadHistory(); },300_000);
    return () => { unsubscribeMarket();unsubscribeConfig();marketSocket.close();configSocket.close();window.clearInterval(timer); };
  },[viewed,selectedTf,applyLiveCandle,reloadCandles,reloadPatterns,reloadScenarios,reloadHistory,reloadTradingConfigs]);
  const save = async () => {
    setSaving(true);setMessage("");
    try {
      if (!selected) throw new Error("Введите актив");
      if (tradingMode !== "PAPER") {
        const availability=await api<{available:boolean;reason?:string}>(`/api/v1/exchange/exchange/instruments/${encodeURIComponent(selected)}/availability?mode=${tradingMode}`);
        if (!availability.available) throw new Error(availability.reason ?? `${selected} недоступен в режиме ${tradingMode}`);
      }
      const configToSave:BacktestSettings={...settings,
        initialCapital:isEditing ? editingInitialCapital ?? settings.initialCapital : settings.initialCapital,
        currentCapital:settings.initialCapital,
      };
      const elliottTimeframes = [settings.elliott.entryTimeframe, settings.elliott.structureTimeframe, settings.elliott.macroTimeframe];
      const dataset = await api<{ timeframes: Array<{ timeframe: string; candles: number }> }>(`/api/v1/backtest/datasets/${encodeURIComponent(selected)}`).catch(() => ({ timeframes: [] }));
      const missing = elliottTimeframes.filter((timeframe) => !dataset.timeframes.some((item) => item.timeframe === timeframe && item.candles > 0));
      if (missing.length) {
        await api("/api/v1/exchange/exchange/history", { method: "POST", body: JSON.stringify({ symbol: selected, timeframes: missing, from_timestamp: Date.now() - 180 * 86400000, to_timestamp: Date.now(), incremental: false, backfill: false }) });
        setMessage(`Для ${selected} запрошены свечи: ${missing.join(", ")}. Конфигурация сохраняется.`);
      }
      await api(`/api/v1/backtest/assets`, { method: "POST", body: JSON.stringify({ symbol: selected, category: "crypto" }) }).catch((error: unknown) => { if (!(error instanceof Error) || !error.message.startsWith("409")) throw error; });
      await api("/api/v1/exchange/exchange/reload-symbols", { method: "POST" });
      await api("/api/v1/execution/trading-configs", { method: "POST", body: JSON.stringify({ symbol: selected, mode: tradingMode, config: configToSave }) });
      setSuppressedActiveAssets((current)=>{const next=new Set(current);next.delete(selected);return next;});
      setViewSymbol(selected);setEditingSymbol(selected);setEditingInitialCapital(configToSave.initialCapital);
      assets.reload();tradingConfigs.reload();setMessage(`Конфигурация ${selected} сохранена в режиме ${tradingMode}.`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  const editActiveConfig = () => {
    if (!selectedConfig?.config) return;
    const raw=typeof selectedConfig.config === "string" ? JSON.parse(selectedConfig.config) as Record<string,unknown> : selectedConfig.config;
    const normalized=snakeToCamel(raw) as Partial<BacktestSettings>;
    const originalInitial=normalized.initialCapital;
    const currentCapital=normalized.currentCapital ?? originalInitial;
    setSettings((current) => ({ ...current,...normalized,initialCapital:currentCapital ?? current.initialCapital,strategy:"ELLIOTT",
      elliott:{ ...current.elliott,...(normalized.elliott as Partial<BacktestSettings["elliott"]> ?? {}) } }));
    setSymbol(selectedConfig.symbol);setTradingMode(selectedConfig.mode);setEditingSymbol(selectedConfig.symbol);
    setEditingInitialCapital(originalInitial ?? currentCapital);setMessage(`Конфигурация ${selectedConfig.symbol} загружена в форму.`);
    setSettingsExpanded(true);
    window.requestAnimationFrame(() => document.getElementById("asset-settings")?.scrollIntoView({ behavior:"smooth",block:"start" }));
  };
  const removeLiveAsset = async () => {
    if (!viewed || !window.confirm(`Удалить ${viewed} из live trading?`)) return;
    const removed=viewed;
    setSaving(true); setMessage("");
    try {
      await api(`/api/v1/execution/trading-configs/${encodeURIComponent(removed)}`, { method: "DELETE" });
      const remaining = activeAssets.filter((item) => item !== removed);
      setSuppressedActiveAssets((current)=>new Set(current).add(removed));
      setViewSymbol(remaining[0] ?? "");
      tradingConfigs.reload();
      setMessage(`Актив ${removed} удалён из live trading.`);
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSaving(false); }
  };
  const pasteConfig = async () => {
    try {
      const parsed = JSON.parse(await navigator.clipboard.readText()) as unknown;
      setSettings((current) => mergeSettingsConfig(current, parsed));
      setMessage("Конфигурация вставлена из буфера обмена.");
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); }
  };
  return <SectionPage title="Рынок" description="Регистрация Elliott-активов и отдельный просмотр их состояния."><Stack spacing={2}>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, width: "100%" }}><Stack spacing={1.5}><Typography variant="h6">Состояние актива</Typography>{activeAssets.length ? <><Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><TextField fullWidth select label="Актив для просмотра" value={viewed} onChange={(e) => setViewSymbol(e.target.value)}>{activeAssets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><TextField fullWidth select label="Просматриваемый таймфрейм" value={selectedTf} onChange={(e) => setSelectedTf(e.target.value)} disabled={!availableTimeframes.length}>{availableTimeframes.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><Button color="error" variant="contained" disabled={!viewed || saving} onClick={() => void removeLiveAsset()} sx={{ minWidth: 190, alignSelf: "center", borderRadius: 1, px: 2.5, py: .5, boxShadow: "none", textTransform: "none", fontWeight: 700, "&:hover": { boxShadow: "0 4px 12px rgba(211,47,47,.2)" } }}>Удалить актив</Button></Stack>
      {currentHistory?.status === "BUILDING" && <Alert severity="info">Исторические paper-сделки рассчитываются на сервере…</Alert>}
      {currentHistory?.status === "WAITING_FOR_DATA" && <Alert severity="warning">Исторический расчёт ждёт загрузки свечей.</Alert>}
      {currentHistory?.status === "FAILED" && <Alert severity="error">Не удалось рассчитать историю: {currentHistory.error}</Alert>}
      <TradingViewChart key={`${viewed}:${selectedTf}`} candles={candles.data?.candles ?? []} isLoading={candles.loading} elliottPatterns={displayedPatterns} entryScenarios={displayedEntries} historicalTrades={currentHistory?.trades ?? []} /></> : <EmptyState text="Нет активных активов для просмотра. Зарегистрируйте актив в настройках ниже." />}</Stack></Paper>
    <Accordion id="asset-settings" expanded={settingsExpanded} onChange={(_,expanded) => setSettingsExpanded(expanded)}
      disableGutters sx={{ width: "100%", border: 1, borderColor: "divider", scrollMarginTop: 90, "&:before": { display: "none" } }}>
      <AccordionSummary expandIcon={<Typography component="span" sx={{ fontSize: 22 }}>⌄</Typography>}><Typography variant="h6">Настройка торгового актива</Typography></AccordionSummary>
      <AccordionDetails><Stack spacing={2}>
        <Stack direction={{ xs:"column",md:"row" }} spacing={1.5}>
          <TextField fullWidth label="Актив" placeholder="BTC-USDT-SWAP" value={symbol} onChange={(e) => { const next=e.target.value.toUpperCase();setSymbol(next);if (next!==editingSymbol) { setEditingSymbol("");setEditingInitialCapital(undefined); } }} />
          <TextField fullWidth select label="Режим торговли" value={tradingMode} onChange={(e) => setTradingMode(e.target.value as TradingMode)}><MenuItem value="PAPER">Paper — локальная имитация</MenuItem><MenuItem value="DEMO">OKX Demo</MenuItem><MenuItem value="PRODUCTION">OKX Production</MenuItem></TextField>
        </Stack>
        <Alert severity={tradingMode === "PRODUCTION" ? "warning" : "info"}>{tradingMode === "PAPER" ? "Ордера исполняются локально и не отправляются на OKX." : tradingMode === "DEMO" ? "Ордера отправляются в демонстрационный контур OKX." : "Реальные ордера. Gateway должен быть подключён к production OKX и явно разрешён для торговли."}</Alert>
        <BacktestSettingsForm isRunning={saving} onChange={setSettings} onRun={() => void save()} progress={0}
          settings={settings} capitalLabel={isEditing ? "Текущий капитал" : "Начальный капитал"}
          submitLabel={isEditing ? "Сохранить изменения" : "Зарегистрировать актив"} />
        <Button variant="outlined" onClick={() => void pasteConfig()} disabled={saving}>Вставить скопированную конфигурацию</Button>
      </Stack></AccordionDetails>
    </Accordion>
    {message && <Alert severity={message.includes("сохранена") || message.includes("загружена") || message.includes("вставлена") || message.includes("удалён") ? "success" : "error"}>{message}</Alert>}
    {selectedConfig && <Paper variant="outlined" sx={{ p:{ xs:2,md:3 } }}><Stack spacing={2}><Stack direction="row" sx={{ alignItems:"center",justifyContent:"space-between" }}><Stack direction="row" spacing={1} sx={{ alignItems:"center" }}><Typography variant="h6">Конфигурация {selectedConfig.symbol}</Typography><Chip label={selectedConfig.mode} color={selectedConfig.mode === "PRODUCTION" ? "error" : selectedConfig.mode === "DEMO" ? "warning" : "default"} /></Stack><Button variant="contained" onClick={editActiveConfig}>Редактировать</Button></Stack><ConfigSummary value={selectedConfig.config} /></Stack></Paper>}
  </Stack></SectionPage>;
}

function snakeToCamel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(snakeToCamel);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()), snakeToCamel(item),
  ]));
}

function parseConfig(value?:BacktestSettings|string):Record<string,unknown> {
  if (!value) return {};
  return typeof value === "string" ? JSON.parse(value) as Record<string,unknown> : value as unknown as Record<string,unknown>;
}

function ConfigSummary({ value }:{ value?:BacktestSettings|string }) {
  const normalized=snakeToCamel(parseConfig(value)) as Partial<BacktestSettings>;
  const elliott=normalized.elliott as Partial<BacktestSettings["elliott"]> | undefined;
  const items=[
    ["Направление",normalized.directionMode ?? "—"],
    ["Таймфреймы",`${elliott?.macroTimeframe ?? "—"} / ${elliott?.structureTimeframe ?? "—"} / ${elliott?.entryTimeframe ?? "—"}`],
    ["Модель входа",elliott?.entryModel ?? "—"],
    ["Риск",`${normalized.riskPerTradePercent ?? 0}%`],
    ["Текущий капитал",normalized.currentCapital ?? normalized.initialCapital ?? "—"],
    ["Маржа",elliott?.useMargin ? `×${normalized.leverage ?? 1}` : "Без маржи"],
    ["Тейки",`${elliott?.takeProfitCount ?? 1} · TP1 ${elliott?.takeProfitRr ?? "—"}R`],
  ];
  return <Stack direction={{ xs:"column",md:"row" }} spacing={1.5}>{items.map(([label,item]) => <Paper key={String(label)} variant="outlined" sx={{ p:1.5,flex:1 }}><Typography variant="caption" color="text.secondary">{label}</Typography><Typography sx={{ mt:.5,fontWeight:600 }}>{item}</Typography></Paper>)}</Stack>;
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

function timeframeWindowLimit(selected: string, macro: string): number {
  const selectedMinutes = timeframeMinutes[selected] ?? 15;
  const macroMinutes = timeframeMinutes[macro] ?? 240;
  return Math.min(200_000, Math.max(500, Math.ceil(500 * macroMinutes / selectedMinutes)));
}

const candleCache = new Map<string, Candle[]>();
const browserCacheTimers = new Map<string,number>();
const candleRequests = new Map<string,Promise<CandlesResponse>>();
const candleSnapshotLimits = new Map<string,number>();
const okxSnapshotKeys = new Set<string>();

function requestCandles(path:string):Promise<CandlesResponse> {
  const pending=candleRequests.get(path);
  if (pending) return pending;
  const request=api<CandlesResponse>(path).finally(() => candleRequests.delete(path));
  candleRequests.set(path,request);return request;
}

function openCandleCache():Promise<IDBDatabase> {
  return new Promise((resolve,reject) => {
    const request=indexedDB.open("smart-money-market-cache",1);
    request.onupgradeneeded=() => request.result.createObjectStore("candles");
    request.onsuccess=() => resolve(request.result);
    request.onerror=() => reject(request.error);
  });
}

async function readBrowserCandles(key:string):Promise<Candle[]> {
  try {
    const database=await openCandleCache();
    return await new Promise((resolve,reject) => {
      const request=database.transaction("candles","readonly").objectStore("candles").get(key);
      request.onsuccess=() => resolve(Array.isArray(request.result) ? request.result as Candle[] : []);
      request.onerror=() => reject(request.error);
    });
  } catch { return []; }
}

function scheduleBrowserCandleWrite(key:string,candles:Candle[]) {
  const previous=browserCacheTimers.get(key);if (previous) window.clearTimeout(previous);
  browserCacheTimers.set(key,window.setTimeout(() => {
    browserCacheTimers.delete(key);
    const write=async () => {
      try {
        const database=await openCandleCache();
        database.transaction("candles","readwrite").objectStore("candles").put(candles,key);
      } catch { /* Browser storage can be unavailable in private mode. */ }
    };
    if ("requestIdleCallback" in window) window.requestIdleCallback(() => void write(),{ timeout:3000 });
    else void write();
  },1500));
}

function candleFingerprint(candles:Candle[]) {
  const first=candles[0];const last=candles.at(-1);
  return `${candles.length}:${first?.timestamp ?? 0}:${last?.timestamp ?? 0}:${last?.open ?? 0}:${last?.high ?? 0}:${last?.low ?? 0}:${last?.close ?? 0}`;
}

function mergeCandles(current: Candle[], incoming: Candle[]): Candle[] {
  return [...new Map([...current, ...incoming].map((item) => [item.timestamp, item])).values()]
    .sort((left, right) => left.timestamp - right.timestamp);
}

function hasCandleGap(candles:Candle[],timeframe:string):boolean {
  const step=(timeframeMinutes[timeframe] ?? 15)*60_000;
  return candles.some((item,index) => index>0 && item.timestamp-candles[index-1].timestamp!==step);
}

function useMarketCandles(symbol: string, timeframe: string, limit: number) {
  const key = `market-v2:${symbol}:${timeframe}`;
  const [data, setData] = useState<CandlesResponse>({ symbol, timeframe, candles: candleCache.get(key) ?? [] });
  const [reloadKey, setReloadKey] = useState(0);
  const [loading,setLoading] = useState(false);
  const cacheRef = useRef(candleCache);
  const fingerprintRef = useRef(`${key}:${candleFingerprint(data.candles)}`);
  const reloadTimer=useRef<number|undefined>(undefined);
  const reload = useCallback(() => {
    if (reloadTimer.current) window.clearTimeout(reloadTimer.current);
    reloadTimer.current=window.setTimeout(() => setReloadKey((current) => current + 1),750);
  }, []);
  useEffect(() => () => { if (reloadTimer.current) window.clearTimeout(reloadTimer.current); },[]);
  const applyLiveCandle=useCallback((incoming:Candle) => {
    const next=mergeCandles(cacheRef.current.get(key) ?? [],[incoming]).slice(-limit);
    cacheRef.current.set(key,next);scheduleBrowserCandleWrite(key,next);
    const fingerprint=`${key}:${candleFingerprint(next)}`;
    if (fingerprint!==fingerprintRef.current) {
      fingerprintRef.current=fingerprint;setData({ symbol,timeframe,candles:next });
    }
  },[key,limit,symbol,timeframe]);

  useEffect(() => {
    let cancelled = false;
    const commit=(next:Candle[]) => {
      const fingerprint=`${key}:${candleFingerprint(next)}`;
      if (fingerprint === fingerprintRef.current) return;
      fingerprintRef.current=fingerprint;setData({ symbol,timeframe,candles:next });
    };
    if (!symbol) { commit([]); return () => { cancelled = true; }; }
    const load = async () => {
      setLoading(true);
      try {
      let collected = cacheRef.current.get(key) ?? await readBrowserCandles(key);
      if (collected.length) {
        cacheRef.current.set(key,collected);
        if (!cancelled) commit(collected.slice(-limit));
      }
      const lastTimestamp=collected.at(-1)?.timestamp;
      const checkedLimit=candleSnapshotLimits.get(key) ?? 0;
      const needsSnapshot=checkedLimit<limit || (checkedLimit===0 && hasCandleGap(collected.slice(-limit),timeframe));
      const path=`/api/v1/data/market/candles?symbol=${encodeURIComponent(symbol)}`
        + `&timeframe=${timeframe}&limit=${needsSnapshot ? limit : 1000}`
        + (needsSnapshot || lastTimestamp === undefined ? "" : `&from=${lastTimestamp}`);
      const databaseRequest=requestCandles(path);
      if (!okxSnapshotKeys.has(key)) {
        okxSnapshotKeys.add(key);
        try {
          const snapshot=await requestCandles(`/api/v1/exchange/exchange/market-candles?symbol=${encodeURIComponent(symbol)}`
            + `&timeframe=${timeframe}&limit=300`);
          collected=mergeCandles(collected,snapshot.candles);
          if (!cancelled)commit(collected.slice(-limit));
        } catch { okxSnapshotKeys.delete(key); }
      }
      const response=await databaseRequest;
      collected=mergeCandles(collected,response.candles);
      if (needsSnapshot) candleSnapshotLimits.set(key,limit);
      const result = collected.slice(-limit);
      cacheRef.current.set(key,result);
      scheduleBrowserCandleWrite(key,result);
      if (!cancelled) commit(result);
      } finally { if (!cancelled) setLoading(false); }
    };
    void load().catch(() => { if (!cancelled) commit(cacheRef.current.get(key) ?? []); });
    return () => { cancelled = true; };
  }, [key, limit, reloadKey, symbol, timeframe]);

  const currentData = data.symbol === symbol && data.timeframe === timeframe
    ? data : { symbol, timeframe, candles: cacheRef.current.get(key) ?? [] };
  return { data: currentData, reload, applyLiveCandle,
    loading: loading || data.symbol !== symbol || data.timeframe !== timeframe };
}
