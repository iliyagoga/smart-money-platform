"use client";

import { Alert, Box, Button, Chip, Dialog, DialogContent, DialogTitle, LinearProgress, MenuItem, Paper, Stack, TablePagination, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { SectionPage } from "../../components/layout/SectionPage";
import { EmptyState } from "../../components/ui/EmptyState";
import { useApiResource } from "../../hooks/useApiResource";
import { usePagination } from "../../hooks/usePagination";
import { api } from "../../lib/api";
import { BacktestReport } from "../../components/backtest/BacktestReport";
import { mapBacktestResult, type BacktestRun } from "../../lib/backtest/apiTypes";
import type { BacktestSettings } from "../../lib/backtest/types";

interface Configuration { id:string;name:string;config:BacktestSettings }
interface PortfolioAsset { symbol:string;configuration_id:string;allocation_percent:number;config:BacktestSettings }
interface Portfolio { id:string;name:string;description:string;assets:PortfolioAsset[];updated_at:string }
const today=()=>new Date().toISOString().slice(0,10);
const initialAsset=():Omit<PortfolioAsset,"config">=>({ symbol:"",configuration_id:"",allocation_percent:100 });

function apiConfig(value:BacktestSettings) {
  const e=value.elliott;
  return { strategy:value.strategy,initial_capital:value.initialCapital,position_size_percent:value.positionSizePercent,
    leverage:value.leverage,fee_percent:value.feePercent,maker_fee_percent:value.makerFeePercent,taker_fee_percent:value.takerFeePercent,
    slippage_percent:value.slippagePercent,funding_percent_per_day:value.fundingPercentPerDay,funding_interval_hours:value.fundingIntervalHours,
    execution_latency_ms:value.executionLatencyMs,tick_size:value.tickSize,lot_size:value.lotSize,minimum_order_size:value.minimumOrderSize,
    volume_participation_percent:value.volumeParticipationPercent,liquidation_fee_percent:value.liquidationFeePercent,
    direction_mode:value.directionMode,risk_per_trade_percent:value.riskPerTradePercent,
    elliott:{ use_margin:e.useMargin,reinvest_profits:e.reinvestProfits,
      macro_timeframe:e.macroTimeframe,structure_timeframe:e.structureTimeframe,entry_timeframe:e.entryTimeframe,atr_period:e.atrPeriod,
      zigzag_reversal_atr:e.zigzagReversalAtr,min_swing_atr:e.minSwingAtr,wave1_min_atr:e.wave1MinAtr,
      wave1_min_efficiency:e.wave1MinEfficiency,wave2_min_retracement:e.wave2MinRetracement,wave2_max_retracement:e.wave2MaxRetracement,
      entry_model:e.entryModel,entry_retracement:e.entryRetracement,entry_expiry_bars:e.entryExpiryBars,
      breakout_buffer_atr:e.breakoutBufferAtr,retest_zone_atr:e.retestZoneAtr,
      displacement_min_atr:e.displacementMinAtr,displacement_min_body_ratio:e.displacementMinBodyRatio,
      displacement_retracement:e.displacementRetracement,sweep_min_wick_ratio:e.sweepMinWickRatio,
      volatility_expansion_ratio:e.volatilityExpansionRatio,volume_expansion_ratio:e.volumeExpansionRatio,
      volume_expansion_min_body_ratio:e.volumeExpansionMinBodyRatio,choch_min_atr:e.chochMinAtr,
      choch_min_body_ratio:e.chochMinBodyRatio,macro_filter:e.macroFilter,adx_period:e.adxPeriod,adx_min:e.adxMin,
      require_di_confirmation:e.requireDiConfirmation,stop_buffer_atr:e.stopBufferAtr,take_profit_count:e.takeProfitCount,
      take_profit_rr:e.takeProfitRr,second_take_profit_rr:e.secondTakeProfitRr,first_take_action:e.firstTakeAction,
      minimum_rr:e.minimumRr,break_even_at_one_r:e.breakEvenAtOneR } };
}

export default function PortfoliosPage() {
  const resource=useApiResource<{ portfolios:Portfolio[] }>("/api/v1/execution/portfolios");
  const configs=useApiResource<{ configurations:Configuration[] }>("/api/v1/execution/configuration-library");
  const [open,setOpen]=useState(false);const [editingId,setEditingId]=useState("");const [name,setName]=useState("");
  const [description,setDescription]=useState("");const [assets,setAssets]=useState([initialAsset()]);
  const [message,setMessage]=useState("");const [error,setError]=useState("");const [busy,setBusy]=useState(false);
  const [runId,setRunId]=useState("");const [from,setFrom]=useState("2025-01-01");
  const [to,setTo]=useState(today());
  const [portfolioRun, setPortfolioRun] = useState<BacktestRun>();
  const [initialCapital, setInitialCapital] = useState(10000);
  const [mode,setMode]=useState("PAPER");
  const running = portfolioRun?.status === "QUEUED" || portfolioRun?.status === "RUNNING";
  const report = useMemo(() => portfolioRun?.result ? mapBacktestResult(portfolioRun.result) : undefined, [portfolioRun?.result]);
  useEffect(() => {
    if (!running || !portfolioRun?.id) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const updated = await api<BacktestRun>(`/api/v1/backtest/backtests/${portfolioRun.id}`);
        if (!active) return;
        setPortfolioRun(updated);
        if (updated.status === "COMPLETED") setMessage("Единый отчёт портфеля готов и сохранён в истории бэктестов.");
        else if (updated.status === "FAILED" || updated.status === "CANCELLED") setError(updated.error || "Прогон портфеля отменён.");
        else timer = setTimeout(() => void poll(), 1000);
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason));
          timer = setTimeout(() => void poll(), 3000);
        }
      }
    };
    timer = setTimeout(() => void poll(), 1000);
    return () => { active = false; clearTimeout(timer); };
  }, [running, portfolioRun?.id]);
  const portfolios=resource.data?.portfolios ?? [];const pagination=usePagination(portfolios);
  const configurationMap=useMemo(()=>new Map((configs.data?.configurations??[]).map(item=>[item.id,item])),[configs.data]);
  const reset=()=>{setEditingId("");setName("");setDescription("");setAssets([initialAsset()]);};
  const edit=(portfolio:Portfolio)=>{setEditingId(portfolio.id);setName(portfolio.name);setDescription(portfolio.description);
    setAssets(portfolio.assets.map(({symbol,configuration_id,allocation_percent})=>({symbol,configuration_id,allocation_percent})));setOpen(true);};
  const save=async()=>{setBusy(true);setError("");try{await api(`/api/v1/execution/portfolios${editingId?`/${editingId}`:""}`,{
    method:editingId?"PUT":"POST",body:JSON.stringify({name,description,assets})});setOpen(false);reset();resource.reload();setMessage("Портфель сохранён.");}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const remove=async(portfolio:Portfolio)=>{if(!window.confirm(`Удалить портфель «${portfolio.name}»?`))return;
    try{await api(`/api/v1/execution/portfolios/${portfolio.id}`,{method:"DELETE"});resource.reload();setMessage("Портфель удалён.");}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}};
  const live=async(portfolio:Portfolio)=>{setBusy(true);setError("");try{const response=await api<{activated_symbols:string[]}>(`/api/v1/execution/portfolios/${portfolio.id}/live`,{
    method:"POST",body:JSON.stringify({mode})});setMessage(`Портфель добавлен в live (${mode}): ${response.activated_symbols.join(", ")}.`);}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const run=async(portfolio:Portfolio)=>{
    setBusy(true);setRunId(portfolio.id);setPortfolioRun(undefined);setError("");setMessage("");
    try {
      const created = await api<{id:string}>("/api/v1/backtest/portfolio-backtests", {
        method: "POST", body: JSON.stringify({
          name: portfolio.name, initial_capital: initialCapital,
          assets: portfolio.assets.map(item => {
            const e = item.config.elliott;
            return { allocation_percent: item.allocation_percent, request: {
              symbol: item.symbol, timeframe: e.entryTimeframe,
              timeframes: [e.entryTimeframe, e.structureTimeframe, e.macroTimeframe],
              candle_limit: 2000000, test_from: Date.parse(`${from}T00:00:00Z`),
              test_to: Date.parse(`${to}T23:59:59.999Z`), config: apiConfig(item.config),
            }};
          }),
        }),
      });
      setPortfolioRun({ id: created.id, symbol: portfolio.name, timeframe: "PORTFOLIO", status: "QUEUED", progress: 0, created_at: new Date().toISOString() });
    } catch(reason) {setError(reason instanceof Error?reason.message:String(reason));}
    finally {setBusy(false);}
  };
  const totalAllocation=assets.reduce((sum,item)=>sum+Number(item.allocation_percent||0),0);
  return <SectionPage title="Портфели" description="Наборы активов и стратегий для общего прогона по датасетам и запуска в live."
    error={error||resource.error||configs.error} isLoading={resource.isLoading||configs.isLoading}
    onReload={()=>{resource.reload();configs.reload();}}>
    {message&&<Alert severity="success" sx={{mb:2}}>{message}</Alert>}
    <Stack direction={{xs:"column",sm:"row"}} spacing={1} sx={{mb:2,justifyContent:"space-between"}}><TextField select size="small" label="Live-режим" value={mode} onChange={event=>setMode(event.target.value)} sx={{minWidth:210}}>
      <MenuItem value="PAPER">Paper</MenuItem><MenuItem value="DEMO">OKX Demo</MenuItem><MenuItem value="PRODUCTION">OKX Production</MenuItem></TextField>
      <Button variant="contained" onClick={()=>{reset();setOpen(true);}}>Создать портфель</Button></Stack>
    {!portfolios.length?<EmptyState text="Портфелей пока нет"/>:<Stack spacing={2}>{pagination.visible.map(portfolio=><Paper key={portfolio.id} variant="outlined" sx={{p:2.5}}><Stack spacing={1.5}>
      <Stack direction={{xs:"column",md:"row"}} sx={{justifyContent:"space-between",gap:1}}><Box><Typography variant="h6">{portfolio.name}</Typography><Typography color="text.secondary">{portfolio.description||"Без описания"}</Typography></Box>
      <Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}><Button size="small" onClick={()=>edit(portfolio)}>Изменить</Button><Button size="small" color="error" onClick={()=>void remove(portfolio)}>Удалить</Button></Stack></Stack>
      <Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}>{portfolio.assets.map(item=><Chip key={item.symbol} label={`${item.symbol} · ${item.allocation_percent}%`} />)}</Stack>
      <Stack direction={{xs:"column",md:"row"}} spacing={1.5}><TextField type="date" size="small" label="Начало датасета" value={from} onChange={event=>setFrom(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/><TextField type="date" size="small" label="Конец датасета" value={to} onChange={event=>setTo(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/>
        <TextField type="number" size="small" label="Капитал портфеля" value={initialCapital} disabled={busy || running}
          onChange={event => setInitialCapital(Number(event.target.value))} slotProps={{htmlInput:{min:0.01,step:100}}}/>
        <Button variant="outlined" disabled={busy || running || !Number.isFinite(initialCapital) || initialCapital <= 0 || !from || !to || from > to} onClick={()=>void run(portfolio)}>Прогнать датасет</Button><Button variant="contained" color={mode==="PRODUCTION"?"error":"primary"} disabled={busy} onClick={()=>void live(portfolio)}>Добавить в live</Button></Stack>
      {runId === portfolio.id && portfolioRun && <Stack spacing={1}>
        {running && <LinearProgress variant="determinate" value={portfolioRun.progress}/>}
        <Typography variant="body2">Портфель: {portfolioRun.status} · {portfolioRun.progress}%</Typography>
        {report && <BacktestReport key={portfolioRun.id} result={report}/>}
      </Stack>}
    </Stack></Paper>)}<TablePagination component="div" {...pagination.paginationProps}/></Stack>}
    <Dialog open={open} onClose={()=>!busy&&setOpen(false)} fullWidth maxWidth="md"><DialogTitle>{editingId?"Редактировать портфель":"Новый портфель"}</DialogTitle><DialogContent dividers><Stack spacing={2}>
      <TextField required label="Название" value={name} onChange={event=>setName(event.target.value)}/><TextField label="Описание" value={description} onChange={event=>setDescription(event.target.value)} multiline minRows={2}/>
      {assets.map((item,index)=><Paper key={index} variant="outlined" sx={{p:2}}><Stack direction={{xs:"column",md:"row"}} spacing={1}><TextField fullWidth label="Актив" placeholder="BTC-USDT-SWAP" value={item.symbol} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,symbol:event.target.value.toUpperCase()}:value))}/>
        <TextField fullWidth select label="Конфигурация" value={item.configuration_id} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,configuration_id:event.target.value}:value))}>{[...configurationMap.values()].map(config=><MenuItem key={config.id} value={config.id}>{config.name}</MenuItem>)}</TextField>
        <TextField label="Доля, %" type="number" value={item.allocation_percent} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,allocation_percent:Number(event.target.value)}:value))} slotProps={{htmlInput:{min:0.01,max:100}}} sx={{width:{xs:"100%",md:160},flexShrink:0}}/>
        <Button color="error" disabled={assets.length===1} onClick={()=>setAssets(current=>current.filter((_,i)=>i!==index))}>Убрать</Button></Stack></Paper>)}
      <Typography color={totalAllocation>100?"error":"text.secondary"}>Распределено: {totalAllocation}% из 100%</Typography><Button variant="outlined" onClick={()=>setAssets(current=>[...current,initialAsset()])}>Добавить актив</Button>
      <Button variant="contained" disabled={busy||!name.trim()||assets.some(item=>!item.symbol||!item.configuration_id)||totalAllocation>100} onClick={()=>void save()}>Сохранить</Button>
    </Stack></DialogContent></Dialog>
  </SectionPage>;
}
