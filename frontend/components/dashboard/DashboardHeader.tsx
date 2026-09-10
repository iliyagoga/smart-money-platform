import { AppBar, Box, Button, Chip, Dialog, DialogContent, DialogTitle, Divider, Drawer, FormControl, FormControlLabel, Radio, RadioGroup, IconButton, Stack, Toolbar, Tooltip, Typography } from "@mui/material";
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
  { label: "Портфели", href: "/portfolios" },
  { label: "Бэктест", href: "/backtest" },
  { label: "Replay", href: "/replay" },
  { label: "Пользователи", href: "/admin/users", adminOnly: true },
  { label: "Профиль", href: "/profile" },
];

interface DashboardHeaderProps { isLive?: boolean; roles?: string[]; username: string }

export function DashboardHeader({ isLive, roles = [], username }: DashboardHeaderProps) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const { mode, palette, toggleColorMode, setPalette } = useColorMode();
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
      sx={{ top: 0, zIndex: 10, borderBottom: 1, borderColor: "divider", backdropFilter: "blur(18px)", bgcolor: "background.paper", px: { xs: .5, sm: 0 } }}
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
          <Typography sx={{ display: { xs: "none", sm: "block" }, fontWeight: 700 }}>Elliott Wave</Typography>
        </Stack>
        <Stack component="nav" direction="row" spacing={0.5} sx={{ display: { xs: "none", xl: "flex" } }}>
          {navigation.filter((item) => !item.adminOnly || roles.includes("admin")).map((item) => (
            <Button component={Link} href={item.href} aria-current={pathname === item.href ? "page" : undefined} key={item.label} color={pathname === item.href ? "primary" : "secondary"} size="small">
              {item.label}
            </Button>
          ))}
        </Stack>
        <Stack direction="row" spacing={{ xs: .25, sm: 1 }} sx={{ alignItems: "center" }}>
          <IconButton onClick={() => setIsMenuOpen(true)} aria-label="Открыть меню" sx={{ display: { xl: "none" } }}>☰</IconButton>
          {isLive !== undefined && <Chip icon={<StatusDot active={isLive} />} label={isLive ? "Live" : "Подключение"} size="small" variant="outlined" sx={{ display: { xs: "none", sm: "inline-flex" } }} />}
          <Typography variant="caption" sx={{ display: { xs: "none", md: "block" }, maxWidth: 130 }} noWrap>{username}</Typography>
          <Tooltip title={mode === "light" ? "Включить тёмную тему" : "Включить светлую тему"}>
            <IconButton onClick={toggleColorMode} aria-label="Переключить цветовую тему" size="small">
              <Box component="span" aria-hidden sx={{ fontSize: 17 }}>{mode === "light" ? "☾" : "☀"}</Box>
            </IconButton>
          </Tooltip>
          <Tooltip title="Цветовая палитра"><IconButton onClick={() => setPaletteOpen(true)} aria-label="Настроить цветовую палитру" size="small">◉</IconButton></Tooltip>
          <Button onClick={() => void logout()} disabled={isLoggingOut} color="secondary" size="small" sx={{ minWidth: { xs: 40, sm: 64 }, px: { xs: .75, sm: 1.5 } }}>
            {isLoggingOut ? "Выходим…" : "Выйти"}
          </Button>
        </Stack>
      </Toolbar>
      <Drawer anchor="right" open={isMenuOpen} onClose={() => setIsMenuOpen(false)}>
        <Stack component="nav" spacing={1} sx={{ width: { xs: "min(88vw, 340px)", sm: 340 }, p: { xs: 2.5, sm: 3 } }}>
          <Typography variant="h6" sx={{ mb: 1 }}>Навигация</Typography>
          <Divider />
          {navigation.filter((item) => !item.adminOnly || roles.includes("admin")).map((item) => (
            <Button
              component={Link}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
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
      <Dialog open={paletteOpen} onClose={() => setPaletteOpen(false)} maxWidth="sm">
        <DialogTitle>Цветовая палитра</DialogTitle><DialogContent>
          <FormControl><RadioGroup value={palette} onChange={event => setPalette(event.target.value as typeof palette)}>
            <FormControlLabel value="lime" control={<Radio />} label="Лайм" />
            <FormControlLabel value="ocean" control={<Radio />} label="Океан" />
            <FormControlLabel value="violet" control={<Radio />} label="Фиолетовая" />
            <FormControlLabel value="amber" control={<Radio />} label="Янтарная" />
          </RadioGroup></FormControl>
          <Button fullWidth sx={{ mt: 2 }} onClick={() => setPaletteOpen(false)}>Готово</Button>
        </DialogContent>
      </Dialog>
    </AppBar>
  );
}
