"use client";

import { AppRouterCacheProvider } from "@mui/material-nextjs/v15-appRouter";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import type { ReactNode } from "react";

const theme = createTheme({
  palette: {
    mode: "dark",
    background: { default: "#090d0c", paper: "#101715" },
    primary: { main: "#b9f24c", contrastText: "#101510" },
    success: { main: "#62d99b" },
    error: { main: "#ff6b6b" },
    text: { primary: "#eef5f1", secondary: "#82928b" },
    divider: "#22302b",
  },
  typography: {
    fontFamily: "Manrope, sans-serif",
    h1: { fontFamily: "Space Grotesk, sans-serif" },
    h2: { fontFamily: "Space Grotesk, sans-serif" },
    h3: { fontFamily: "Space Grotesk, sans-serif" },
  },
  shape: { borderRadius: 3 },
});

interface ThemeRegistryProps {
  children: ReactNode;
}

export function ThemeRegistry({ children }: ThemeRegistryProps) {
  return (
    <AppRouterCacheProvider>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </AppRouterCacheProvider>
  );
}
