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
  wide?: boolean;
}

export function SectionPage({ children, description, error = "", isLoading = false, onReload, title, wide = false }: SectionPageProps) {
  const { username } = useAuth();
  return (
    <AuthenticatedPage>
      <Container component="main" maxWidth={false} sx={{
        maxWidth: wide ? 1800 : 1500, width: "100%", pb: 7.5, px: { xs: 2, md: 4.75 },
      }}>
        <DashboardHeader isLive username={username} />
        <Stack direction={{ xs: "column", sm: "row" }} sx={{ py: { xs: 4, md: 6 }, justifyContent: "space-between", gap: 2 }}>
          <Box>
            <Typography className="eyebrow" color="primary.main">SMART MONEY</Typography>
            <Typography variant="h3" sx={{ mt: 1 }}>{title}</Typography>
            <Typography color="text.secondary" sx={{ mt: 1 }}>{description}</Typography>
          </Box>
          {onReload && <Button variant="outlined" onClick={onReload} disabled={isLoading} sx={{ alignSelf: { sm: "flex-end" } }}>↻ Обновить</Button>}
        </Stack>
        {error && <Alert severity="error" variant="outlined" sx={{ mb: 2 }} action={onReload
          ? <Button color="inherit" size="small" onClick={onReload}>Повторить</Button>
          : undefined}>{error}</Alert>}
        {isLoading ? <Stack sx={{ py: 10, alignItems: "center" }}><CircularProgress /></Stack> : children}
      </Container>
    </AuthenticatedPage>
  );
}
