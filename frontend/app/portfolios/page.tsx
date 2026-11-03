"use client";

import { Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, LinearProgress, MenuItem, Paper, Stack, TablePagination, TextField, Typography } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { SectionPage } from "../../components/layout/SectionPage";
import { EmptyState } from "../../components/ui/EmptyState";
import { useApiResource } from "../../hooks/useApiResource";
import { usePagination } from "../../hooks/usePagination";
import { api } from "../../lib/api";
import { BacktestReport } from "../../components/backtest/BacktestReport";
import { mapBacktestResult, type BacktestRun } from "../../lib/backtest/apiTypes";
import type { BacktestSettings } from "../../lib/backtest/types";
import { toBackendBacktestConfig } from "../../lib/backtest/backendConfig";

interface Configuration { id:string;name:string;config:BacktestSettings }
interface PortfolioAsset { symbol:string;configuration_id:string;allocation_percent:number;config:BacktestSettings }
interface Portfolio { id:string;name:string;description:string;assets:PortfolioAsset[];updated_at:string }
interface AssetValidation {
  symbol:string;valid:boolean;errors:string[];budget?:number;price?:number;lot_size?:number;
  minimum_quantity?:number;minimum_contracts?:number;take_quantities?:number[];required_margin?:number;
  risk_percent?:number;risk_budget?:number;max_stop_distance?:number;max_stop_percent?:number;leverage?:number;
}
interface LiveValidation { valid:boolean;assets:AssetValidation[] }
interface LivePreview { portfolio:Portfolio;mode:string;capital:number;capital_mode:"ALLOCATED"|"SEQUENTIAL";validation:LiveValidation }
const amount=(value?:number)=>value===undefined?"—":value.toLocaleString("ru-RU",{maximumSignificantDigits:10});
const today=()=>new Date().toISOString().slice(0,10);
const initialAsset=():Omit<PortfolioAsset,"config">=>({ symbol:"",configuration_id:"",allocation_percent:100 });

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
  const [liveCapital, setLiveCapital] = useState<number | "">("");
  const [capitalMode,setCapitalMode]=useState<"ALLOCATED"|"SEQUENTIAL">("ALLOCATED");
  const [mode,setMode]=useState("PAPER");
  const [livePreview,setLivePreview]=useState<LivePreview>();
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
  const live=async(portfolio:Portfolio)=>{if(typeof liveCapital!=="number"||!Number.isFinite(liveCapital)||liveCapital<=0)return;
    setBusy(true);setError("");setMessage("");try{const validation=await api<LiveValidation>(`/api/v1/execution/portfolios/${portfolio.id}/live`,{
    method:"POST",body:JSON.stringify({mode,capital:liveCapital,capital_mode:capitalMode,validate_only:true})});
    setLivePreview({portfolio,mode,capital:liveCapital,capital_mode:capitalMode,validation});}
    catch(reason){setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const activateLive=async()=>{if(!livePreview?.validation.valid)return;
    const preview=livePreview;setBusy(true);setError("");try{
      const response=await api<{activated_symbols:string[]}>(`/api/v1/execution/portfolios/${preview.portfolio.id}/live`,{
        method:"POST",body:JSON.stringify({mode:preview.mode,capital:preview.capital,capital_mode:preview.capital_mode})});
      setLivePreview(undefined);setMessage(`Портфель добавлен в live (${preview.mode}): ${response.activated_symbols.join(", ")}.`);
    }catch(reason){setLivePreview(undefined);setError(reason instanceof Error?reason.message:String(reason));}finally{setBusy(false);}};
  const run=async(portfolio:Portfolio)=>{
    setBusy(true);setRunId(portfolio.id);setPortfolioRun(undefined);setError("");setMessage("");
    try {
      const created = await api<{id:string}>("/api/v1/backtest/portfolio-backtests", {
        method: "POST", body: JSON.stringify({
          name: portfolio.name, initial_capital: initialCapital, capital_mode: capitalMode,
          assets: portfolio.assets.map(item => {
            const e = item.config.elliott;
            return { allocation_percent: item.allocation_percent, request: {
              symbol: item.symbol, timeframe: e.entryTimeframe,
              timeframes: [e.entryTimeframe, e.structureTimeframe, e.macroTimeframe],
              candle_limit: 2000000, test_from: Date.parse(`${from}T00:00:00Z`),
              test_to: Date.parse(`${to}T23:59:59.999Z`), config: toBackendBacktestConfig(item.config),
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
    <Dialog open={!!livePreview} onClose={()=>{if(!busy)setLivePreview(undefined);}} maxWidth="md" fullWidth>
      <DialogTitle>Проверка перед запуском · {livePreview?.portfolio.name}</DialogTitle>
      <DialogContent><Stack spacing={2}>
        <Typography>Режим: {livePreview?.mode}. Капитал: {amount(livePreview?.capital)} USDT.</Typography>
        {livePreview?.mode==="PRODUCTION"&&<Alert severity="warning">Подтверждение запуска включает реальную торговлю.</Alert>}
        <Alert severity={livePreview?.validation.valid?"info":"error"}>
          {livePreview?.mode==="PAPER"?"Конфигурация PAPER проверена. Биржевой расчёт лотов доступен для DEMO и PRODUCTION.":livePreview?.validation.valid?"Проверка пройдена. Перед запуском данные будут проверены повторно.":"Запуск заблокирован. Исправьте бюджет или конфигурацию проблемных активов."}
        </Alert>
        {livePreview?.validation.assets.map(asset=><Paper key={asset.symbol} variant="outlined" sx={{p:2}}>
          <Stack spacing={.5}><Typography sx={{fontWeight:600}}>{asset.symbol}</Typography>
            {asset.errors.map(error=><Typography key={error} color="error">{error}</Typography>)}
            {asset.minimum_quantity!==undefined&&<>
              <Typography>Бюджет: {amount(asset.budget)} USDT · Цена: {amount(asset.price)} USDT · Плечо: {amount(asset.leverage)}×</Typography>
              <Typography>Шаг количества: {amount(asset.lot_size)} · Минимальная позиция: {amount(asset.minimum_quantity)} монет{" "}
                ({amount(asset.minimum_contracts)} контрактов)</Typography>
              <Typography>Объёмы тейков минимальной позиции: {asset.take_quantities?.map(quantity=>amount(quantity)).join(" + ")} монет</Typography>
              <Typography>Необходимое обеспечение: {amount(asset.required_margin)} USDT</Typography>
              <Typography>Риск: {amount(asset.risk_percent)}% бюджета = {amount(asset.risk_budget)} USDT</Typography>
              <Typography>Максимальное расстояние до стопа для минимальной позиции: {amount(asset.max_stop_distance)} USDT{" "}
                ({amount(asset.max_stop_percent)}%)</Typography>
            </>}
          </Stack></Paper>)}
        {livePreview?.mode!=="PAPER"&&<Typography variant="body2" color="text.secondary">Расчёт минимальных объёмов выполнен по текущей цене. Фактический объём зависит от входа и стопа будущего сигнала. Комиссии и проскальзывание в оценку обеспечения не включены.</Typography>}
      </Stack></DialogContent>
      <DialogActions><Button disabled={busy} onClick={()=>setLivePreview(undefined)}>Закрыть</Button>
        <Button variant="contained" color={livePreview?.mode==="PRODUCTION"?"error":"primary"} disabled={busy||!livePreview?.validation.valid} onClick={()=>void activateLive()}>Запустить {livePreview?.mode}</Button>
      </DialogActions>
    </Dialog>
    <Stack direction={{xs:"column",sm:"row"}} spacing={1} sx={{mb:2,justifyContent:"space-between"}}><TextField select size="small" label="Live-режим" value={mode} onChange={event=>setMode(event.target.value)} sx={{minWidth:210}}>
      <MenuItem value="PAPER">Paper</MenuItem><MenuItem value="DEMO">OKX Demo</MenuItem><MenuItem value="PRODUCTION">OKX Production</MenuItem></TextField>
      <TextField size="small" type="number" label="Live-капитал, USDT" value={liveCapital}
        onChange={event=>setLiveCapital(event.target.value===""?"":Number(event.target.value))}
        slotProps={{htmlInput:{min:0.01,step:100}}} sx={{minWidth:210}}/>
      <Button variant="contained" onClick={()=>{reset();setOpen(true);}}>Создать портфель</Button></Stack>
    {!portfolios.length?<EmptyState text="Портфелей пока нет"/>:<Stack spacing={2}>{pagination.visible.map(portfolio=><Paper key={portfolio.id} variant="outlined" sx={{p:2.5}}><Stack spacing={1.5}>
      <Stack direction={{xs:"column",md:"row"}} sx={{justifyContent:"space-between",gap:1}}><Box><Typography variant="h6">{portfolio.name}</Typography><Typography color="text.secondary">{portfolio.description||"Без описания"}</Typography></Box>
      <Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}><Button size="small" onClick={()=>edit(portfolio)}>Изменить</Button><Button size="small" color="error" onClick={()=>void remove(portfolio)}>Удалить</Button></Stack></Stack>
      <Stack direction="row" spacing={1} sx={{flexWrap:"wrap"}}>{portfolio.assets.map(item=><Chip key={item.symbol} label={`${item.symbol} · ${item.allocation_percent}%`} />)}</Stack>
      <Stack direction={{xs:"column",xl:"row"}} spacing={1.5}><TextField type="date" size="small" label="Начало датасета" value={from} onChange={event=>setFrom(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/><TextField type="date" size="small" label="Конец датасета" value={to} onChange={event=>setTo(event.target.value)} slotProps={{inputLabel:{shrink:true}}}/>
        <TextField type="number" size="small" label="Капитал портфеля" value={initialCapital} disabled={busy || running}
          onChange={event => setInitialCapital(Number(event.target.value))} slotProps={{htmlInput:{min:0.01,step:100}}}/>
        <TextField select size="small" label="Режим капитала" value={capitalMode} disabled={busy||running}
          onChange={event=>setCapitalMode(event.target.value as "ALLOCATED"|"SEQUENTIAL")} sx={{minWidth:250}}>
          <MenuItem value="ALLOCATED">Параллельно · фиксированные доли</MenuItem>
          <MenuItem value="SEQUENTIAL">Последовательно · общий капитал</MenuItem>
        </TextField>
        <Button variant="outlined" disabled={busy || running || !Number.isFinite(initialCapital) || initialCapital <= 0 || !from || !to || from > to || (capitalMode==="ALLOCATED"&&portfolio.assets.reduce((sum,item)=>sum+item.allocation_percent,0)>100)} onClick={()=>void run(portfolio)}>Прогнать датасет</Button><Button variant="contained" color={mode==="PRODUCTION"?"error":"primary"} disabled={busy||typeof liveCapital!=="number"||!Number.isFinite(liveCapital)||liveCapital<=0||(capitalMode==="ALLOCATED"&&portfolio.assets.reduce((sum,item)=>sum+item.allocation_percent,0)>100)} onClick={()=>void live(portfolio)}>Добавить в live</Button></Stack>
      {capitalMode==="SEQUENTIAL"&&<Typography variant="body2" color="text.secondary">Одновременно открыта только одна сделка. Для каждой новой сделки доля актива считается от актуального капитала.</Typography>}
      {runId === portfolio.id && portfolioRun && <Stack spacing={1}>
        {running && <LinearProgress variant="determinate" value={portfolioRun.progress}/>}
        <Typography variant="body2">Портфель: {portfolioRun.status} · {portfolioRun.progress}%</Typography>
        {report && <BacktestReport key={portfolioRun.id} result={report}/>}
      </Stack>}
    </Stack></Paper>)}<TablePagination component="div" {...pagination.paginationProps}/></Stack>}
    <Dialog open={open} onClose={()=>!busy&&setOpen(false)} maxWidth="lg"><DialogTitle>{editingId?"Редактировать портфель":"Новый портфель"}</DialogTitle><DialogContent dividers><Stack spacing={2}>
      <TextField required label="Название" value={name} onChange={event=>setName(event.target.value)}/><TextField label="Описание" value={description} onChange={event=>setDescription(event.target.value)} multiline minRows={2}/>
      {assets.map((item,index)=><Paper key={index} variant="outlined" sx={{p:2}}><Stack direction={{xs:"column",md:"row"}} spacing={1}><TextField fullWidth label="Актив" placeholder="BTC-USDT-SWAP" value={item.symbol} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,symbol:event.target.value.toUpperCase()}:value))}/>
        <TextField fullWidth select label="Конфигурация" value={item.configuration_id} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,configuration_id:event.target.value}:value))}>{[...configurationMap.values()].map(config=><MenuItem key={config.id} value={config.id}>{config.name}</MenuItem>)}</TextField>
        <TextField label="Доля, %" type="number" value={item.allocation_percent} onChange={event=>setAssets(current=>current.map((value,i)=>i===index?{...value,allocation_percent:Number(event.target.value)}:value))} slotProps={{htmlInput:{min:0.01,max:100}}} sx={{width:{xs:"100%",md:160},flexShrink:0}}/>
        <Button color="error" disabled={assets.length===1} onClick={()=>setAssets(current=>current.filter((_,i)=>i!==index))}>Убрать</Button></Stack></Paper>)}
      <Typography color="text.secondary">Сумма долей: {totalAllocation}%. В параллельном режиме сумма долей не должна превышать 100%. В последовательном режиме каждый актив использует свою долю общего капитала.</Typography><Button variant="outlined" onClick={()=>setAssets(current=>[...current,initialAsset()])}>Добавить актив</Button>
      <Button variant="contained" disabled={busy||!name.trim()||assets.some(item=>!item.symbol||!item.configuration_id)} onClick={()=>void save()}>Сохранить</Button>
    </Stack></DialogContent></Dialog>
  </SectionPage>;
}
