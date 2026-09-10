"use client";

import {
  Alert, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControl, FormControlLabel, InputLabel, MenuItem, OutlinedInput, Paper, Select,
  Stack, Switch, TextField, Typography,
} from "@mui/material";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../../../components/auth/AuthProvider";
import { SectionPage } from "../../../components/layout/SectionPage";
import { api } from "../../../lib/api";

const roleOptions = ["viewer", "trader", "admin"] as const;
const roleLabels: Record<string,string> = { viewer:"Просмотр",trader:"Трейдер",admin:"Администратор" };

interface ManagedUser {
  id:string;username:string;email:string;first_name:string;last_name:string;enabled:boolean;roles:string[];
}
interface UserDraft { enabled:boolean;roles:string[] }
interface CreateDraft {
  username:string;email:string;first_name:string;last_name:string;password:string;
  temporary_password:boolean;roles:string[];
}

const emptyCreate:CreateDraft={
  username:"",email:"",first_name:"",last_name:"",password:"",temporary_password:true,roles:["viewer"],
};

export default function AdminUsersPage() {
  const { roles }=useAuth();
  const isAdmin=roles.includes("admin");
  const [users,setUsers]=useState<ManagedUser[]>([]);
  const [drafts,setDrafts]=useState<Record<string,UserDraft>>({});
  const [loading,setLoading]=useState(false);
  const [savingId,setSavingId]=useState("");
  const [error,setError]=useState("");
  const [message,setMessage]=useState("");
  const [createOpen,setCreateOpen]=useState(false);
  const [createDraft,setCreateDraft]=useState<CreateDraft>(emptyCreate);

  const load=useCallback(async () => {
    if (!isAdmin) return;
    setLoading(true);setError("");
    try {
      const response=await api<{users:ManagedUser[]}>("/api/v1/admin/users");
      setUsers(response.users);
      setDrafts(Object.fromEntries(response.users.map((user) => [user.id,{ enabled:user.enabled,roles:user.roles }])));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setLoading(false); }
  },[isAdmin]);

  useEffect(() => { void load(); },[load]);
  const sortedUsers=useMemo(() => [...users].sort((left,right) => left.username.localeCompare(right.username)),[users]);

  const saveUser=async (user:ManagedUser) => {
    const draft=drafts[user.id];if (!draft || !draft.roles.length) { setError("Назначьте хотя бы одну роль.");return; }
    setSavingId(user.id);setError("");setMessage("");
    try {
      const updated=await api<ManagedUser>(`/api/v1/admin/users/${encodeURIComponent(user.id)}`,{
        method:"PATCH",body:JSON.stringify(draft),
      });
      setUsers((current) => current.map((item) => item.id === updated.id ? updated : item));
      setDrafts((current) => ({ ...current,[updated.id]:{ enabled:updated.enabled,roles:updated.roles } }));
      setMessage(`Пользователь ${updated.username} обновлён.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSavingId(""); }
  };

  const createUser=async () => {
    if (!createDraft.username.trim() || createDraft.password.length < 8 || !createDraft.roles.length) {
      setError("Укажите логин, пароль не короче 8 символов и хотя бы одну роль.");return;
    }
    setSavingId("create");setError("");setMessage("");
    try {
      const created=await api<ManagedUser>("/api/v1/admin/users",{
        method:"POST",body:JSON.stringify({ ...createDraft,username:createDraft.username.trim(),email:createDraft.email.trim() }),
      });
      setUsers((current) => [...current,created]);
      setDrafts((current) => ({ ...current,[created.id]:{ enabled:created.enabled,roles:created.roles } }));
      setCreateDraft(emptyCreate);setCreateOpen(false);setMessage(`Пользователь ${created.username} создан.`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setSavingId(""); }
  };

  if (!isAdmin) return <SectionPage title="Пользователи" description="Управление доступом к платформе.">
    <Alert severity="error">Эта страница доступна только администратору.</Alert>
  </SectionPage>;

  return <SectionPage title="Пользователи" description="Создание учётных записей, блокировка доступа и управление ролями." error={error} isLoading={loading} onReload={() => void load()}>
    <Stack spacing={2}>
      {message && <Alert severity="success" onClose={() => setMessage("")}>{message}</Alert>}
      <Stack direction={{xs:"column",sm:"row"}} sx={{ justifyContent:"space-between",alignItems:{sm:"center"},gap:1.5 }}>
        <Typography color="text.secondary">Пользователей: {users.length}</Typography>
        <Button variant="contained" onClick={() => setCreateOpen(true)}>Создать пользователя</Button>
      </Stack>
      <Stack spacing={1.5}>{sortedUsers.map((user) => {
        const draft=drafts[user.id] ?? { enabled:user.enabled,roles:user.roles };
        const changed=draft.enabled !== user.enabled || [...draft.roles].sort().join() !== [...user.roles].sort().join();
        return <Paper key={user.id} variant="outlined" sx={{ p:{xs:2,md:2.5} }}><Stack direction={{xs:"column",lg:"row"}} sx={{ gap:2,alignItems:{lg:"center"} }}>
          <Box sx={{ minWidth:240,flex:1 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems:"center",flexWrap:"wrap" }}>
              <Typography variant="h6">{user.username}</Typography>
              {!user.enabled && <Chip size="small" color="default" label="Заблокирован" />}
            </Stack>
            <Typography variant="body2" color="text.secondary">{[user.first_name,user.last_name].filter(Boolean).join(" ") || "Имя не указано"}</Typography>
            <Typography variant="caption" color="text.secondary">{user.email || "Email не указан"}</Typography>
          </Box>
          <FormControl sx={{ minWidth:{xs:"100%",sm:300} }}>
            <InputLabel id={`roles-${user.id}`}>Роли</InputLabel>
            <Select multiple labelId={`roles-${user.id}`} value={draft.roles} input={<OutlinedInput label="Роли" />}
              renderValue={(selected) => selected.map((role) => roleLabels[role] ?? role).join(", ")}
              onChange={(event) => setDrafts((current) => ({ ...current,[user.id]:{ ...draft,roles:typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value } }))}>
              {roleOptions.map((role) => <MenuItem key={role} value={role}>
                <Checkbox checked={draft.roles.includes(role)} />{roleLabels[role]}
              </MenuItem>)}
            </Select>
          </FormControl>
          <FormControlLabel control={<Switch checked={draft.enabled} onChange={(event) => setDrafts((current) => ({ ...current,[user.id]:{ ...draft,enabled:event.target.checked } }))} />} label={draft.enabled ? "Активен" : "Заблокирован"} />
          <Button variant="contained" disabled={!changed || savingId === user.id || !draft.roles.length} onClick={() => void saveUser(user)} sx={{ minWidth:120 }}>
            {savingId === user.id ? "Сохраняем…" : "Сохранить"}
          </Button>
        </Stack></Paper>;
      })}</Stack>
      {!sortedUsers.length && <Alert severity="info">Пользователи не найдены.</Alert>}
    </Stack>
    <Dialog open={createOpen} onClose={() => savingId !== "create" && setCreateOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>Новый пользователь</DialogTitle>
      <DialogContent><Stack spacing={2} sx={{ pt:1 }}>
        <TextField required label="Логин" autoFocus value={createDraft.username} onChange={(event) => setCreateDraft((current) => ({...current,username:event.target.value}))} />
        <TextField label="Email" type="email" value={createDraft.email} onChange={(event) => setCreateDraft((current) => ({...current,email:event.target.value}))} />
        <Stack direction={{xs:"column",sm:"row"}} spacing={2}>
          <TextField fullWidth label="Имя" value={createDraft.first_name} onChange={(event) => setCreateDraft((current) => ({...current,first_name:event.target.value}))} />
          <TextField fullWidth label="Фамилия" value={createDraft.last_name} onChange={(event) => setCreateDraft((current) => ({...current,last_name:event.target.value}))} />
        </Stack>
        <TextField required label="Пароль" type="password" helperText="Минимум 8 символов" value={createDraft.password} onChange={(event) => setCreateDraft((current) => ({...current,password:event.target.value}))} />
        <FormControl><InputLabel id="new-user-roles">Роли</InputLabel><Select multiple labelId="new-user-roles" value={createDraft.roles} input={<OutlinedInput label="Роли" />}
          renderValue={(selected) => selected.map((role) => roleLabels[role] ?? role).join(", ")}
          onChange={(event) => setCreateDraft((current) => ({...current,roles:typeof event.target.value === "string" ? event.target.value.split(",") : event.target.value}))}>
          {roleOptions.map((role) => <MenuItem key={role} value={role}>
            <Checkbox checked={createDraft.roles.includes(role)} />{roleLabels[role]}
          </MenuItem>)}
        </Select></FormControl>
        <FormControlLabel control={<Checkbox checked={createDraft.temporary_password} onChange={(event) => setCreateDraft((current) => ({...current,temporary_password:event.target.checked}))} />} label="Потребовать смену пароля при первом входе" />
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setCreateOpen(false)} disabled={savingId === "create"}>Отмена</Button><Button variant="contained" onClick={() => void createUser()} disabled={savingId === "create"}>{savingId === "create" ? "Создаём…" : "Создать"}</Button></DialogActions>
    </Dialog>
  </SectionPage>;
}
