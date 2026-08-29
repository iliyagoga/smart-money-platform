"use client";

import { Alert, Button, Checkbox, FormControlLabel, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { SectionPage } from "../../components/layout/SectionPage";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import { api } from "../../lib/api";

const timeframes = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"];
export default function MarketPage() {
  const assets = useTradingAssets(); const [symbol, setSymbol] = useState("");
  const [strategy, setStrategy] = useState("ELLIOTT"); const [capital, setCapital] = useState(10000);
  const [risk, setRisk] = useState(1); const [leverage, setLeverage] = useState(1);
  const [frames, setFrames] = useState(["M15", "H1", "H4"]); const [saving, setSaving] = useState(false); const [message, setMessage] = useState("");
  const selected = symbol || assets.assets[0] || "";
  useEffect(() => { if (!symbol && assets.assets.length) setSymbol(assets.assets[0]); }, [assets.assets, symbol]);
  const save = async () => { setSaving(true); setMessage(""); try {
    if (!selected) throw new Error("Выберите актив");
    await api(`/api/v1/backtest/assets`, { method: "POST", body: JSON.stringify({ symbol: selected, category: "crypto" }) }).catch((error: unknown) => { if (!(error instanceof Error) || !error.message.startsWith("409")) throw error; });
    await api("/api/v1/execution/trading-configs", { method: "POST", body: JSON.stringify({ symbol: selected, mode: "SIMULATION", config: { strategy, initial_capital: capital, risk_per_trade_percent: risk, leverage, timeframes: frames } }) });
    await api("/api/v1/exchange/exchange/reload-symbols", { method: "POST" }).catch(() => undefined); assets.reload();
    setMessage(`Актив ${selected} добавлен в автономную симуляцию. Конфигурация сохранена в БД.`);
  } catch (reason) { setMessage(reason instanceof Error ? reason.message : String(reason)); } finally { setSaving(false); } };
  return <SectionPage title="Рынок" description="Активация автономной торговли без отправки реальных заявок."><Paper variant="outlined" sx={{ p: { xs: 2, md: 3 }, maxWidth: 760 }}><Stack spacing={2}>
    <Typography variant="h6">Настройка торгового актива</Typography>
    <TextField select label="Актив" value={selected} onChange={(e) => setSymbol(e.target.value)}>{assets.assets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}</TextField>
    <TextField select label="Стратегия" value={strategy} onChange={(e) => setStrategy(e.target.value)}><MenuItem value="ELLIOTT">Elliott Wave</MenuItem><MenuItem value="SMC">Smart Money Concept</MenuItem></TextField>
    <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}><TextField fullWidth label="Начальный капитал" type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value))} /><TextField fullWidth label="Риск на сделку, %" type="number" value={risk} onChange={(e) => setRisk(Number(e.target.value))} /><TextField fullWidth label="Плечо" type="number" value={leverage} onChange={(e) => setLeverage(Number(e.target.value))} /></Stack>
    <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: .5 }}>{timeframes.map((item) => <FormControlLabel key={item} label={item} control={<Checkbox checked={frames.includes(item)} onChange={(e) => setFrames((current) => e.target.checked ? [...current, item] : current.filter((x) => x !== item))} />} />)}</Stack>
    <FormControlLabel control={<Checkbox checked disabled />} label="Симуляция торгов (paper) — реальные ордера не отправляются" />
    <Alert severity="info">После запуска актив отслеживается автономно сервисами системы, даже если страница закрыта.</Alert>
    <Button variant="contained" onClick={() => void save()} disabled={saving || !selected || !frames.length}>{saving ? "Сохраняем…" : "Запустить торговый актив"}</Button>
    {message && <Typography color={message.includes("добавлен") ? "success.main" : "error.main"}>{message}</Typography>}
  </Stack></Paper></SectionPage>;
}
