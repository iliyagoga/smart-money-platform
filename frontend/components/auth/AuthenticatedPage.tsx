"use client";

import { Button, CircularProgress, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { keycloak } from "../../lib/auth";
import { useAuth } from "./AuthProvider";

export function AuthenticatedPage({ children }: { children: ReactNode }) {
  const { error, isAuthenticated, isReady } = useAuth();

  if (!isReady) {
    return <Stack sx={{ minHeight: "100vh", alignItems: "center", justifyContent: "center" }}><CircularProgress /></Stack>;
  }
  if (error) {
    return <Stack sx={{ minHeight: "100vh", alignItems: "center", justifyContent: "center" }}><Typography>{error}</Typography></Stack>;
  }
  if (!isAuthenticated) {
    return (
      <Stack sx={{ minHeight: "100vh", alignItems: "center", justifyContent: "center", gap: 2 }}>
        <Typography variant="h5">Для просмотра раздела войдите в систему</Typography>
        <Button variant="contained" onClick={() => void keycloak().login({ redirectUri: location.href })}>Войти</Button>
      </Stack>
    );
  }
  return children;
}
