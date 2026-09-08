"use client";

import { Alert, Box, Button, CircularProgress, Container, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";
import { useAuth } from "../auth/AuthProvider";
import { AuthenticatedPage } from "../auth/AuthenticatedPage";
import { DashboardHeader } from "../dashboard/DashboardHeader";

interface SectionPageProps {
  children: ReactNode;
  description: string;
  error?: string;
  isLoading?: boolean;
  onReload?: () => void;
  title: string;
}

export function SectionPage({ children, description, error = "", isLoading = false, onReload, title }: SectionPageProps) {
  const { username } = useAuth();
  return (
    <AuthenticatedPage>
      <Container component="main" maxWidth={false} sx={{
        maxWidth: 1920,
        width: "100%",
        mx: "auto",
        pb: { xs: 4, md: 7.5 },
        px: { xs: 1.5, sm: 2.5, md: 3, lg: 4 },
      }}>
        <DashboardHeader isLive username={username} />
        <Stack direction={{ xs: "column", sm: "row" }} sx={{ py: { xs: 3, md: 4.5 }, justifyContent: "space-between", gap: 2 }}>
          <Box sx={{ minWidth: 0 }}>
            <Typography className="eyebrow" color="primary.main">ELLIOTT WAVE</Typography>
            <Typography component="h1" variant="h3" sx={{ mt: 1, fontSize: { xs: 30, sm: 36, md: 44 } }}>{title}</Typography>
            <Typography color="text.secondary" sx={{ mt: 1, maxWidth: 900 }}>{description}</Typography>
          </Box>
          {onReload && <Button variant="outlined" onClick={onReload} disabled={isLoading} sx={{ alignSelf: { xs: "stretch", sm: "flex-end" }, flexShrink: 0 }}>↻ Обновить</Button>}
        </Stack>
        {error && <Alert severity="error" variant="outlined" sx={{ mb: 2 }} action={onReload
          ? <Button color="inherit" size="small" onClick={onReload}>Повторить</Button>
          : undefined}>{error}</Alert>}
        {isLoading ? <Stack sx={{ py: 10, alignItems: "center" }}><CircularProgress /></Stack> : children}
      </Container>
    </AuthenticatedPage>
  );
}
