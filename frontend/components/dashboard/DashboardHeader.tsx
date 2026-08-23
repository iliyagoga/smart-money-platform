import { AppBar, Box, Button, Chip, IconButton, Stack, Toolbar, Tooltip, Typography } from "@mui/material";
import { useState } from "react";
import { useColorMode } from "../../app/ThemeRegistry";
import { keycloak } from "../../lib/auth";
import { StatusDot } from "../ui/StatusDot";

const navigation = [
  { label: "Обзор", href: "#overview" },
  { label: "Рынок", href: "#events" },
  { label: "Сценарии", href: "#services" },
  { label: "Сделки", href: "#positions" },
  { label: "Обучение", href: "#insights" },
];

interface DashboardHeaderProps { isLive: boolean; username: string }

export function DashboardHeader({ isLive, username }: DashboardHeaderProps) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const { mode, toggleColorMode } = useColorMode();

  const logout = async () => {
    setIsLoggingOut(true);
    await keycloak().logout({ redirectUri: location.origin });
  };

  return (
    <AppBar
      position="sticky"
      color="inherit"
      elevation={0}
      sx={{ top: 0, zIndex: 10, borderBottom: 1, borderColor: "divider", backdropFilter: "blur(18px)", bgcolor: "background.paper" }}
    >
      <Toolbar disableGutters sx={{ minHeight: "76px !important", justifyContent: "space-between" }}>
        <Stack component="a" href="#overview" direction="row" spacing={1.5} sx={{ alignItems: "center", color: "inherit", textDecoration: "none" }}>
          <Box
            sx={{
              display: "grid",
              placeContent: "center",
              width: 38,
              height: 38,
              borderRadius: 2.5,
              bgcolor: "primary.main",
              color: "primary.contrastText",
            }}
          >
            <Typography variant="caption" sx={{ fontWeight: 700 }}>SM</Typography>
          </Box>
          <Typography sx={{ display: { xs: "none", sm: "block" }, fontWeight: 700 }}>Smart Money</Typography>
        </Stack>
        <Stack component="nav" direction="row" spacing={0.5} sx={{ display: { xs: "none", lg: "flex" } }}>
          {navigation.map((item) => (
            <Button component="a" href={item.href} key={item.label} color="secondary" size="small">
              {item.label}
            </Button>
          ))}
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Chip icon={<StatusDot active={isLive} />} label={isLive ? "Live" : "Подключение"} size="small" variant="outlined" />
          <Typography variant="caption" sx={{ display: { xs: "none", md: "block" }, maxWidth: 130 }} noWrap>{username}</Typography>
          <Tooltip title={mode === "light" ? "Включить тёмную тему" : "Включить светлую тему"}>
            <IconButton onClick={toggleColorMode} aria-label="Переключить цветовую тему" size="small">
              <Box component="span" aria-hidden sx={{ fontSize: 17 }}>{mode === "light" ? "☾" : "☀"}</Box>
            </IconButton>
          </Tooltip>
          <Button onClick={() => void logout()} disabled={isLoggingOut} color="secondary" size="small">
            {isLoggingOut ? "Выходим…" : "Выйти"}
          </Button>
        </Stack>
      </Toolbar>
    </AppBar>
  );
}
