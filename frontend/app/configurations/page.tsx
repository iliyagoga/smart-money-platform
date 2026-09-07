"use client";

import { Accordion, AccordionDetails, AccordionSummary, Alert, Box, Button, Chip, Dialog, DialogContent, DialogTitle, Paper, Stack, TablePagination, TextField, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import { BacktestSettingsForm } from "../../components/backtest/BacktestSettingsForm";
import { SectionPage } from "../../components/layout/SectionPage";
import { EmptyState } from "../../components/ui/EmptyState";
import { useApiResource } from "../../hooks/useApiResource";
import { api } from "../../lib/api";
import { defaultBacktestSettings } from "../../lib/backtest/defaultSettings";
import type { BacktestSettings } from "../../lib/backtest/types";
import { mergeSettingsConfig } from "../../lib/backtest/configClipboard";

interface SavedConfiguration {
  id:string;name:string;description:string;config:BacktestSettings;created_at:string;updated_at:string;
}
interface ConfigurationResponse { configurations:SavedConfiguration[] }
const freshSettings=():BacktestSettings => ({ ...defaultBacktestSettings,elliott:{ ...defaultBacktestSettings.elliott } });

export default function ConfigurationsPage() {
  const resource=useApiResource<ConfigurationResponse>("/api/v1/execution/configuration-library");
  const [editingId,setEditingId]=useState("");const [name,setName]=useState("");const [description,setDescription]=useState("");
  const [settings,setSettings]=useState<BacktestSettings>(freshSettings);const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState("");const [actionError,setActionError]=useState("");
  const [editorOpen,setEditorOpen]=useState(false);const [page,setPage]=useState(0);const [rowsPerPage,setRowsPerPage]=useState(10);
  const importValue=(value:unknown,suggestedName="",suggestedDescription="") => {
    if (!value || typeof value!=="object") throw new Error("Не удалось прочитать конфигурацию");
    const wrapper=value as { name?:string;description?:string };
    setSettings((current)=>mergeSettingsConfig(current,value));
    setEditingId("");setName(wrapper.name ?? suggestedName);setDescription(wrapper.description ?? suggestedDescription);
    setMessage("Конфигурация из бэктеста загружена. Укажите имя и сохраните её.");setEditorOpen(true);
  };
  useEffect(()=>{
    const transferred=sessionStorage.getItem("configuration-import");if(!transferred)return;
    sessionStorage.removeItem("configuration-import");
    try { importValue(JSON.parse(transferred) as unknown); }
    catch(reason) { setActionError(reason instanceof Error ? reason.message:String(reason)); }
  },[]);
  const paste=async() => {
    setActionError("");
    try { importValue(JSON.parse(await navigator.clipboard.readText()) as unknown); }
    catch(reason) { setActionError(reason instanceof Error ? reason.message:String(reason)); }
  };
  const reset=() => { setEditingId("");setName("");setDescription("");setSettings(freshSettings()); };
  const create=() => { reset();setActionError("");setMessage("");setEditorOpen(true); };
  const edit=(item:SavedConfiguration) => {
    setEditingId(item.id);setName(item.name);setDescription(item.description);
    setSettings({ ...item.config,elliott:{ ...item.config.elliott } });setMessage("");setEditorOpen(true);
  };
  const save=async() => {
    if (!name.trim()) { setActionError("Введите имя конфигурации");return; }
    setSaving(true);setActionError("");setMessage("");
    try {
      await api(`/api/v1/execution/configuration-library${editingId ? `/${editingId}` : ""}`,{
        method:editingId ? "PUT":"POST",body:JSON.stringify({ name:name.trim(),description:description.trim(),config:settings }),
      });
      setMessage(editingId ? "Конфигурация обновлена":"Конфигурация сохранена");reset();setEditorOpen(false);resource.reload();
    } catch(reason) { setActionError(reason instanceof Error ? reason.message:String(reason)); }
    finally { setSaving(false); }
  };
  const remove=async(item:SavedConfiguration) => {
    if (!window.confirm(`Удалить конфигурацию «${item.name}»?`)) return;
    setActionError("");
    try { await api(`/api/v1/execution/configuration-library/${item.id}`,{ method:"DELETE" });if(editingId===item.id){reset();setEditorOpen(false);}resource.reload();setMessage("Конфигурация удалена"); }
    catch(reason) { setActionError(reason instanceof Error ? reason.message:String(reason)); }
  };
  const copy=async(item:SavedConfiguration) => {
    setActionError("");
    try {
      await navigator.clipboard.writeText(JSON.stringify(item.config,null,2));
      setMessage(`Конфигурация «${item.name}» скопирована`);
    } catch(reason) { setActionError(reason instanceof Error ? reason.message:String(reason)); }
  };
  const error=actionError || resource.error;
  const configurations=resource.data?.configurations ?? [];
  const visible=configurations.slice(page*rowsPerPage,page*rowsPerPage+rowsPerPage);
  useEffect(()=>{
    const lastPage=Math.max(0,Math.ceil(configurations.length/rowsPerPage)-1);
    if(page>lastPage)setPage(lastPage);
  },[configurations.length,page,rowsPerPage]);
  return <SectionPage title="Конфигурации" description="Именованная библиотека настроек торговой системы Elliott."
    error={error} isLoading={resource.isLoading} onReload={resource.reload}>
    <Stack direction={{ xs:"column",sm:"row" }} spacing={1} sx={{ mb:2,justifyContent:"flex-end" }}>
      <Button variant="outlined" onClick={()=>void paste()}>Вставить из бэктеста</Button><Button variant="contained" onClick={create}>Создать конфигурацию</Button>
    </Stack>
    {message && <Alert severity="success" sx={{ mb:2 }}>{message}</Alert>}
    <Paper variant="outlined" sx={{ p:{ xs:1.5,md:3 },width:"100%" }}><Typography variant="h6" sx={{ mb:2 }}>
      Сохранённые конфигурации · {configurations.length}</Typography>
      {!configurations.length ? <EmptyState text="Сохранённых конфигураций пока нет" /> : <Stack spacing={1.5}>
        {visible.map((item)=><Paper key={item.id} variant="outlined" sx={{ p:2 }}><Stack spacing={1.5}>
          <Stack direction="row" sx={{ justifyContent:"space-between",gap:1 }}><Box><Typography sx={{ fontWeight:700 }}>{item.name}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt:.5 }}>{item.description || "Без описания"}</Typography></Box>
            <Chip size="small" label={item.config.elliott?.entryModel ?? "ELLIOTT"} /></Stack>
          <Typography variant="caption" color="text.secondary">Обновлено {new Date(item.updated_at).toLocaleString("ru-RU")}</Typography>
          <Stack direction="row" spacing={1}><Button variant="contained" size="small" onClick={()=>edit(item)}>Редактировать</Button>
            <Button variant="outlined" size="small" onClick={()=>void copy(item)}>Копировать</Button>
            <Button color="error" size="small" onClick={()=>void remove(item)}>Удалить</Button></Stack>
          <Accordion disableGutters><AccordionSummary expandIcon={<Typography>⌄</Typography>}><Typography variant="body2">Просмотреть JSON</Typography></AccordionSummary>
            <AccordionDetails><Box component="pre" sx={{ m:0,p:1.5,overflow:"auto",bgcolor:"action.hover",fontSize:11 }}>{JSON.stringify(item.config,null,2)}</Box></AccordionDetails>
          </Accordion></Stack></Paper>)}
        <TablePagination component="div" count={configurations.length} page={page} rowsPerPage={rowsPerPage}
          rowsPerPageOptions={[5,10,25,50]} labelRowsPerPage="Конфигураций на странице"
          onPageChange={(_,value)=>setPage(value)} onRowsPerPageChange={(event)=>{setRowsPerPage(Number(event.target.value));setPage(0);}} />
      </Stack>}
    </Paper>
    <Dialog open={editorOpen} onClose={()=>!saving&&setEditorOpen(false)} fullWidth maxWidth="xl" scroll="paper">
      <DialogTitle>{editingId ? "Редактирование конфигурации":"Новая конфигурация"}</DialogTitle>
      <DialogContent dividers><Stack spacing={2}><Paper variant="outlined" sx={{ p:2.5 }}><Stack spacing={2}>
        <TextField required label="Имя" value={name} onChange={(event)=>setName(event.target.value)}
          placeholder="Например, Elliott H1 консервативная" slotProps={{ htmlInput:{ maxLength:120 } }} />
        <TextField label="Описание" value={description} onChange={(event)=>setDescription(event.target.value)} multiline minRows={3}
          placeholder="Назначение, рынок и особенности этой конфигурации" slotProps={{ htmlInput:{ maxLength:1000 } }} />
      </Stack></Paper><BacktestSettingsForm isRunning={saving} onChange={setSettings} onRun={()=>void save()} progress={0}
        settings={settings}   submitLabel={editingId ? "Сохранить изменения":"Сохранить конфигурацию"} />
        <Button disabled={saving} onClick={()=>setEditorOpen(false)}>Закрыть</Button></Stack></DialogContent>
    </Dialog>
  </SectionPage>;
}
