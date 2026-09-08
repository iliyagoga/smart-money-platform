"use client";

import { AppRouterCacheProvider } from "@mui/material-nextjs/v15-appRouter";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import type { PaletteMode } from "@mui/material";
import { createContext, useContext, useMemo, useSyncExternalStore } from "react";
import type { ReactNode } from "react";

interface ColorModeContextValue {
  mode: PaletteMode;
  palette: PaletteName;
  toggleColorMode: () => void;
  setPalette: (palette: PaletteName) => void;
}

export type PaletteName = "lime" | "ocean" | "violet" | "amber";

const ColorModeContext = createContext<ColorModeContextValue | undefined>(undefined);
const colorModeKey = "smart-money-color-mode";
const colorModeEvent = "smart-money-color-mode-change";
const paletteKey = "smart-money-palette";
const palettes: Record<PaletteName, { light: string; dark: string }> = {
  lime: { light: "#517d00", dark: "#b9f24c" }, ocean: { light: "#006b7d", dark: "#55d8ef" },
  violet: { light: "#6845a5", dark: "#c5a3ff" }, amber: { light: "#9a5b00", dark: "#ffc35c" },
};

const subscribeToColorMode = (listener: () => void) => {
  window.addEventListener("storage", listener);
  window.addEventListener(colorModeEvent, listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener(colorModeEvent, listener);
  };
};

const getColorMode = (): PaletteMode => localStorage.getItem(colorModeKey) === "dark" ? "dark" : "light";
const getPalette = (): PaletteName => {
  const value = localStorage.getItem(paletteKey) as PaletteName | null;
  return value && value in palettes ? value : "lime";
};
const getDefaultColorMode = (): PaletteMode => "light";
const getDefaultPalette = (): PaletteName => "lime";

const buildTheme = (mode: PaletteMode, palette: PaletteName) => createTheme({
  palette: {
    mode,
    background: {
      default: mode === "light" ? "#f5f7f6" : "#090d0c",
      paper: mode === "light" ? "#ffffff" : "#101715",
    },
    primary: {
      main: palettes[palette][mode],
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
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: { root: { minHeight: 40, borderRadius: 10 } },
    },
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          transition: "border-color 180ms ease, box-shadow 180ms ease, transform 180ms ease",
        },
      },
    },
    MuiDialog: {
      defaultProps: { fullWidth: true, maxWidth: "md" },
      styleOverrides: {
        paper: {
          width: "calc(100% - 32px)",
          maxHeight: "calc(100% - 32px)",
          margin: 16,
          "@media (min-width:600px)": {
            width: "calc(100% - 48px)",
            maxHeight: "calc(100% - 48px)",
            margin: 24,
          },
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: { root: { padding: "24px 28px 16px" } },
    },
    MuiDialogContent: {
      styleOverrides: { root: { padding: "24px 28px" } },
    },
    MuiDialogActions: {
      styleOverrides: { root: { padding: "16px 28px 24px", gap: 8 } },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontSize: 12, fontWeight: 700, letterSpacing: "0.04em", whiteSpace: "nowrap" },
        root: { borderColor: mode === "light" ? "#e7ece9" : "#22302b" },
      },
    },
    MuiTableContainer: {
      styleOverrides: { root: { overflowX: "auto" } },
    },
    MuiTablePagination: {
      styleOverrides: {
        toolbar: {
          minHeight: 56,
          paddingLeft: 8,
          paddingRight: 8,
          flexWrap: "wrap",
        },
      },
    },
    MuiTextField: { defaultProps: { size: "small" } },
    MuiTooltip: { defaultProps: { arrow: true } },
  },
});

export function useColorMode(): ColorModeContextValue {
  const context = useContext(ColorModeContext);
  if (!context) throw new Error("useColorMode must be used inside ThemeRegistry");
  return context;
}

export function ThemeRegistry({ children }: { children: ReactNode }) {
  const mode = useSyncExternalStore(subscribeToColorMode, getColorMode, getDefaultColorMode);
  const palette = useSyncExternalStore(subscribeToColorMode, getPalette, getDefaultPalette);
  const theme = useMemo(() => buildTheme(mode, palette), [mode, palette]);
  const colorMode = useMemo(() => ({
    mode, palette,
    toggleColorMode: () => {
      localStorage.setItem(colorModeKey, mode === "light" ? "dark" : "light");
      window.dispatchEvent(new Event(colorModeEvent));
    },
    setPalette: (next: PaletteName) => {
      localStorage.setItem(paletteKey, next); window.dispatchEvent(new Event(colorModeEvent));
    },
  }), [mode, palette]);

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
