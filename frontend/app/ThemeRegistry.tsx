"use client";

import { AppRouterCacheProvider } from "@mui/material-nextjs/v15-appRouter";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import type { PaletteMode } from "@mui/material";
import { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

interface ColorModeContextValue {
  mode: PaletteMode;
  toggleColorMode: () => void;
}

const ColorModeContext = createContext<ColorModeContextValue | undefined>(undefined);
const colorModeKey = "smart-money-color-mode";
const colorModeEvent = "smart-money-color-mode-change";

const subscribeToColorMode = (listener: () => void) => {
  window.addEventListener("storage", listener);
  window.addEventListener(colorModeEvent, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(colorModeEvent, listener);
  };
};

const getColorMode = (): PaletteMode => localStorage.getItem(colorModeKey) === "dark" ? "dark" : "light";
const getDefaultColorMode = (): PaletteMode => "light";

const buildTheme = (mode: PaletteMode) => createTheme({
  palette: {
    mode,
    background: {
      default: mode === "light" ? "#f5f7f6" : "#090d0c",
      paper: mode === "light" ? "#ffffff" : "#101715",
    },
    primary: {
      main: mode === "light" ? "#517d00" : "#b9f24c",
      contrastText: mode === "light" ? "#ffffff" : "#101510",
    },
    secondary: { main: mode === "light" ? "#52605a" : "#9aaba3" },
    success: { main: mode === "light" ? "#168653" : "#62d99b" },
    error: { main: "#d94a4a" },
    text: {
      primary: mode === "light" ? "#17201c" : "#eef5f1",
      secondary: mode === "light" ? "#66736d" : "#82928b",
    },
    divider: mode === "light" ? "#dfe6e2" : "#22302b",
  },
  typography: {
    fontFamily: "Montserrat, sans-serif",
    h1: { fontFamily: "Montserrat, sans-serif", fontWeight: 650, letterSpacing: "-0.045em" },
    h2: { fontFamily: "Montserrat, sans-serif", fontWeight: 650, letterSpacing: "-0.025em" },
    h3: { fontFamily: "Montserrat, sans-serif", fontWeight: 650, letterSpacing: "-0.025em" },
    button: { fontWeight: 650, textTransform: "none" },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiDialog: {
      defaultProps: { fullWidth: true, maxWidth: "lg" },
      styleOverrides: { paper: { margin: 16, width: "calc(100% - 32px)" } },
    },
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          transition: "border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease",
        },
      },
    },
  },
});

export function useColorMode(): ColorModeContextValue {
  const context = useContext(ColorModeContext);
  if (!context) throw new Error("useColorMode must be used inside ThemeRegistry");
  return context;
}

export function ThemeRegistry({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribeToColorMode, getColorMode, getDefaultColorMode);
  const theme = useMemo(() => buildTheme(mode), [mode]);
  const colorMode = useMemo(() => ({
    mode,
    toggleColorMode: () => {
      localStorage.setItem(colorModeKey, mode === "light" ? "dark" : "light");
      window.dispatchEvent(new Event(colorModeEvent));
    },
  }), [mode]);

  return (
    <AppRouterCacheProvider>
      <ColorModeContext.Provider value={colorMode}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          {children}
        </ThemeProvider>
      </ColorModeContext.Provider>
    </AppRouterCacheProvider>
  );
}
