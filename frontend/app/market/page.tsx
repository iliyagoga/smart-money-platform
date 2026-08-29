"use client";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { TradingViewChart } from "../../components/market/TradingViewChart";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import { EventSocket } from "../../lib/socket";
import { defaultBacktestSettings } from "../../lib/backtest/defaultSettings";
import type { BacktestSettings } from "../../lib/backtest/types";
import type { CandlesResponse } from "../../lib/types";

const allTimeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
type TradingConfig = { symbol: string; mode: string; status: string };
type TradingConfigsResponse = { configs: TradingConfig[] };
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
  const query = useMemo(() => `symbol=${encodeURIComponent(viewed)}&timeframe=${selectedTf}`, [viewed, selectedTf]);
  const candles = useApiResource<CandlesResponse>(`/api/v1/exchange/exchange/market-candles?${query}&limit=100`);
  const reloadCandles = candles.reload;
  useEffect(() => {
    if (!symbol && assets.assets.length) setSymbol(assets.assets[0]);
    if (!viewSymbol && activeAssets.length) setViewSymbol(activeAssets[0]);
  }, [assets.assets, activeAssets, symbol, viewSymbol]);
  useEffect(() => { const socket = new EventSocket(["candle.*"]); const unsubscribe = socket.subscribe((event) => { if (event.payload?.symbol === viewed) reloadCandles(); }); void socket.connect(); const timer = window.setInterval(() => reloadCandles(), 15_000); return () => { unsubscribe(); socket.close(); window.clearInterval(timer); }; }, [viewed, reloadCandles]);
  const save = async () => { setSaving(true); setMessage(""); try { if (!selected) throw new Error("Введите актив"); const elliottTimeframes = [settings.elliott.entryTimeframe, settings.elliott.structureTimeframe, settings.elliott.macroTimeframe]; const dataset = await api<{ timeframes: Array<{ timeframe: string; candles: number }> }>(`/api/v1/backtest/datasets/${encodeURIComponent(selected)}`).catch(() => ({ timeframes: [] })); const missing = elliottTimeframes.filter((timeframe) => !dataset.timeframes.some((item) => item.timeframe === timeframe && item.candles > 0)); if (missing.length) { await api("/api/v1/exchange/exchange/history", { method: "POST", body: JSON.stringify({ symbol: selected, timeframes: missing, from_timestamp: Date.now() - 180 * 86400000, to_timestamp: Date.now(), incremental: false, backfill: false }) }); setMessage(`Для ${selected} запрошены свечи: ${missing.join(", ")}. Конфигурация сохраняется.`); } await api(`/api/v1/backtest/assets`, { method: "POST", body: JSON.stringify({ symbol: selected, category: "crypto" }) }).catch((error: unknown) => { if (!(error instanceof Error) || !error.message.startsWith("409")) throw error; }); await api("/api/v1/execution/trading-configs", { method: "POST", body: JSON.stringify({ symbol: selected, mode: "SIMULATION", config: settings }) }); await api("/api/v1/exchange/exchange/reload-symbols", { method: "POST" }).catch(() => undefined); assets.reload(); tradingConfigs.reload(); setMessage(`Актив ${selected} зарегистрирован в автономной симуляции.`); } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); } finally { setSaving(false); } };
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
      <AccordionDetails><Stack spacing={2}><TextField fullWidth label="Актив" placeholder="BTC-USDT-SWAP" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} /><Alert severity="info">Параметры ниже полностью совпадают с Elliott-настройками бэктеста и сохраняются в конфигурации автоторговли.</Alert><BacktestSettingsForm isRunning={saving} onChange={setSettings} onRun={() => void save()} progress={0} settings={settings} templates={[]} elliottOnly submitLabel="Зарегистрировать актив" /><Button variant="outlined" onClick={() => void pasteConfig()} disabled={saving}>Вставить скопированную конфигурацию</Button>{message && <Typography color={message.includes("зарегистрирован") || message.includes("вставлена") ? "success.main" : "error.main"}>{message}</Typography>}</Stack></AccordionDetails>
    </Accordion>
    <Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, width: "100%" }}><Stack spacing={1.5}><Typography variant="h6">Состояние актива</Typography><Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><TextField fullWidth select label="Актив для просмотра" value={viewed} onChange={(e) => setViewSymbol(e.target.value)}>{activeAssets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField><TextField fullWidth select label="Просматриваемый таймфрейм" value={selectedTf} onChange={(e) => setSelectedTf(e.target.value)} disabled={!availableTimeframes.length}>{availableTimeframes.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField></Stack>{viewed ? <TradingViewChart candles={candles.data?.candles ?? []} /> : <Typography color="text.secondary">Нет активных активов для просмотра.</Typography>}</Stack></Paper>
  </Stack></SectionPage>;
}

function snakeToCamel(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(snakeToCamel);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [
    key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase()), snakeToCamel(item),
  ]));
}
