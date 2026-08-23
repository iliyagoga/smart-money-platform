"use client";

import { Box, Button, CircularProgress, IconButton, Stack, Tooltip, Typography } from "@mui/material";
import { useState } from "react";
import Dashboard from "../components/Dashboard";
import { useAuth } from "../components/auth/AuthProvider";
import { keycloak } from "../lib/auth";
import { useColorMode } from "./ThemeRegistry";

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return <Stack component="main" sx={{ minHeight: "100vh", alignItems: "center", justifyContent: "center" }}>{children}</Stack>;
}

export default function Home() {
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const { error, isAuthenticated, isReady } = useAuth();
  const { mode, toggleColorMode } = useColorMode();

  const login = async () => {
    setIsLoggingIn(true);
    await keycloak().login({ redirectUri: location.origin });
  };

  if (!isReady) {
    return (
      <CenteredMessage>
        <CircularProgress size={36} />
        <Typography color="text.secondary">Подключаем защищённую сессию…</Typography>
      </CenteredMessage>
    );
  }
  if (error) {
    return (
      <CenteredMessage>
        <Typography variant="h4">Не удалось запустить приложение</Typography>
        <Typography color="text.secondary">{error}</Typography>
        <Button variant="outlined" onClick={() => location.reload()} sx={{ mt: 2 }}>Попробовать снова</Button>
      </CenteredMessage>
    );
  }
  if (!isAuthenticated) {
    return (
      <Box
        component="main"
        sx={{ minHeight: "100vh", display: "grid", gridTemplateColumns: { md: "3fr 2fr" }, gap: { md: 8 }, p: { xs: 3, md: "7vw" } }}
      >
        <Tooltip title={mode === "light" ? "Включить тёмную тему" : "Включить светлую тему"}>
          <IconButton onClick={toggleColorMode} aria-label="Переключить цветовую тему" sx={{ position: "fixed", top: 24, right: 24 }}>
            <Box component="span" aria-hidden>{mode === "light" ? "☾" : "☀"}</Box>
          </IconButton>
        </Tooltip>
        <Box component="section" sx={{ alignSelf: "center" }}>
          <Typography className="eyebrow">SMART MONEY PLATFORM</Typography>
          <Typography component="h1" variant="h1" sx={{ fontSize: "clamp(48px, 7vw, 96px)", lineHeight: 0.98, my: 3 }}>
            Рынок становится<br /><Box component="em" color="primary.main" sx={{ fontStyle: "normal" }}>структурой.</Box>
          </Typography>
          <Typography color="text.secondary" sx={{ fontSize: 18 }}>Сценарии, риск и исполнение в одном живом контуре.</Typography>
          <Button variant="contained" size="large" onClick={() => void login()} disabled={isLoggingIn} sx={{ mt: 4.25, px: 3, py: 1.5 }}>
            {isLoggingIn ? "Переходим…" : "Войти через Keycloak →"}
          </Button>
        </Box>
        <Box
          component="aside"
          sx={{
            display: { xs: "none", md: "grid" },
            position: "relative",
            overflow: "hidden",
            minHeight: 560,
            border: 1,
            borderColor: "divider",
            borderRadius: 5,
            placeItems: "end start",
            p: 4,
            background: "radial-gradient(circle at 65% 35%, color-mix(in srgb, currentColor 8%, transparent), transparent 40%)",
          }}
        >
          <Box
            sx={{
              position: "absolute",
              width: 360,
              height: 360,
              border: 1,
              borderColor: "primary.main",
              borderRadius: "50%",
              top: "15%",
              left: "18%",
            }}
          />
          <Box>
            <Typography className="eyebrow">LIVE INTELLIGENCE</Typography>
            <Typography variant="h5" sx={{ mt: 1 }}>Решения на основе структуры рынка</Typography>
          </Box>
        </Box>
      </Box>
    );
  }
  return <Dashboard />;
}
