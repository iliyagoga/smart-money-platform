"use client";

import { Box, Button, CircularProgress, Stack, Typography } from "@mui/material";
import { useEffect, useState } from "react";
import Dashboard from "../components/Dashboard";
import { keycloak } from "../lib/auth";

function CenteredMessage({ children }: { children: React.ReactNode }) {
  return <Stack component="main" sx={{ minHeight: "100vh", alignItems: "center", justifyContent: "center" }}>{children}</Stack>;
}

export default function Home() {
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    keycloak()
      .init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
      .then(setIsAuthenticated)
      .catch((reason: unknown) => setError(String(reason)))
      .finally(() => setIsReady(true));
  }, []);

  if (!isReady) {
    return (
      <CenteredMessage>
        <CircularProgress size={36} />
        <Typography color="text.secondary">Подключаем защищённую сессию…</Typography>
      </CenteredMessage>
    );
  }
  if (error) {
    return <CenteredMessage><Typography variant="h4">Не удалось запустить приложение</Typography><Typography>{error}</Typography></CenteredMessage>;
  }
  if (!isAuthenticated) {
    return (
      <Box component="main" sx={{ minHeight: "100vh", display: "grid", gridTemplateColumns: { md: "3fr 2fr" }, p: "8vw" }}>
        <Box component="section" sx={{ alignSelf: "center" }}>
          <Typography className="eyebrow">SMART MONEY PLATFORM</Typography>
          <Typography component="h1" variant="h1" sx={{ fontSize: "clamp(48px, 7vw, 96px)", lineHeight: 0.98, my: 3 }}>
            Рынок становится<br /><Box component="em" color="primary.main" sx={{ fontStyle: "normal" }}>структурой.</Box>
          </Typography>
          <Typography color="text.secondary" sx={{ fontSize: 18 }}>Сценарии, риск и исполнение в одном живом контуре.</Typography>
          <Button variant="contained" size="large" onClick={() => keycloak().login({ redirectUri: location.origin })} sx={{ mt: 4.25 }}>
            Войти через Keycloak →
          </Button>
        </Box>
        <Box component="aside" sx={{ display: { xs: "none", md: "grid" }, border: 1, borderColor: "divider", placeItems: "end start", p: 3.75 }}>
          <Typography>LIVE INTELLIGENCE</Typography>
        </Box>
      </Box>
    );
  }
  return <Dashboard />;
}
