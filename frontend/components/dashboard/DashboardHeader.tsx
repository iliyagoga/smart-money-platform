import { AppBar, Box, Button, Chip, Divider, Drawer, IconButton, Stack, Toolbar, Tooltip, Typography } from "@mui/material";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useColorMode } from "../../app/ThemeRegistry";
import { keycloak } from "../../lib/auth";
import { StatusDot } from "../ui/StatusDot";

const navigation = [
  { label: "Обзор", href: "/" },
  { label: "Рынок", href: "/market" },
  { label: "Сделки", href: "/trades" },
  { label: "Конфигурации", href: "/configurations" },
  { label: "Бэктест", href: "/backtest" },
  { label: "Replay", href: "/replay" },
];

interface DashboardHeaderProps { isLive: boolean; username: string }

export function DashboardHeader({ isLive, username }: DashboardHeaderProps) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { mode, toggleColorMode } = useColorMode();
  const pathname = usePathname();

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
        <Stack component={Link} href="/" direction="row" spacing={1.5} sx={{ alignItems: "center", color: "inherit", textDecoration: "none" }}>
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
            <Button component={Link} href={item.href} key={item.label} color={pathname === item.href ? "primary" : "secondary"} size="small">
              {item.label}
            </Button>
          ))}
        </Stack>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <IconButton onClick={() => setIsMenuOpen(true)} aria-label="Открыть меню" sx={{ display: { lg: "none" } }}>☰</IconButton>
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
      <Drawer anchor="right" open={isMenuOpen} onClose={() => setIsMenuOpen(false)}>
        <Stack component="nav" spacing={1} sx={{ width: 280, p: 3 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>Навигация</Typography>
          <Divider />
          {navigation.map((item) => (
            <Button
              component={Link}
              href={item.href}
              key={item.label}
              onClick={() => setIsMenuOpen(false)}
              variant={pathname === item.href ? "contained" : "text"}
              sx={{ justifyContent: "flex-start" }}
            >
              {item.label}
            </Button>
          ))}
        </Stack>
      </Drawer>
    </AppBar>
  );
}
