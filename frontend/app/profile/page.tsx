"use client";

import { Alert, Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { useState } from "react";
import { useAuth } from "../../components/auth/AuthProvider";
import { SectionPage } from "../../components/layout/SectionPage";
import { keycloak } from "../../lib/auth";

export default function ProfilePage() {
  const { roles, username } = useAuth();
  const [redirecting,setRedirecting] = useState(false);
  const changePassword = async () => {
    setRedirecting(true);
    try {
      await keycloak().login({ action:"UPDATE_PASSWORD",redirectUri:location.href });
    } finally { setRedirecting(false); }
  };
  return <SectionPage title="Профиль" description="Данные учётной записи и безопасность.">
    <Paper variant="outlined" sx={{ p:{ xs:2,md:3 },maxWidth:720 }}><Stack spacing={2.5}>
      <Stack spacing={.5}><Typography variant="caption" color="text.secondary">ПОЛЬЗОВАТЕЛЬ</Typography>
        <Typography variant="h5">{username}</Typography></Stack>
      <Stack spacing={1}><Typography variant="caption" color="text.secondary">РОЛИ</Typography>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap:"wrap" }}>{roles.map((role) => <Chip key={role} label={role} />)}</Stack></Stack>
      <Alert severity="info">Пароль изменяется в защищённой форме Keycloak. После сохранения вы вернётесь в профиль.</Alert>
      <Button variant="contained" onClick={() => void changePassword()} disabled={redirecting} sx={{ alignSelf:{ sm:"flex-start" } }}>
        {redirecting ? "Переходим…" : "Изменить пароль"}
      </Button>
    </Stack></Paper>
  </SectionPage>;
}
