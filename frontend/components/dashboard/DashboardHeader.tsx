import { AppBar, Box, Button, Stack, Toolbar, Typography } from "@mui/material";
import { keycloak } from "../../lib/auth";
import { StatusDot } from "../ui/StatusDot";

const navigation = ["Обзор", "Рынок", "Сценарии", "Сделки", "Обучение"];

interface DashboardHeaderProps { isLive: boolean; username: string }

export function DashboardHeader({ isLive, username }: DashboardHeaderProps) {
  const logout = () => keycloak().logout({ redirectUri: location.origin });

  return (
    <AppBar position="static" color="transparent" elevation={0} sx={{ borderBottom: 1, borderColor: "divider" }}>
      <Toolbar disableGutters sx={{ minHeight: "76px !important", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Box sx={{ display: "grid", placeContent: "center", width: 34, height: 34, bgcolor: "primary.main", color: "primary.contrastText" }}>
            <Typography variant="caption" sx={{ fontWeight: 700 }}>SM</Typography>
          </Box>
          <Typography sx={{ fontWeight: 700 }}>Smart Money</Typography>
        </Stack>
        <Stack component="nav" direction="row" spacing={3.5} sx={{ display: { xs: "none", md: "flex" } }}>
          {navigation.map((item, index) => (
            <Button key={item} color={index === 0 ? "inherit" : "secondary"} size="small">{item}</Button>
          ))}
        </Stack>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
          <StatusDot active={isLive} />
          <Typography variant="caption" sx={{ display: { xs: "none", sm: "block" } }}>{username}</Typography>
          <Button onClick={logout} color="secondary" size="small">Выйти</Button>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
