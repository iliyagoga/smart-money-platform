import { Box, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface PanelProps { children: ReactNode; title: string; meta: string; minHeight?: number }

export function Panel({ children, title, meta, minHeight = 300 }: PanelProps) {
  return (
    <Paper
      variant="outlined"
      sx={{
        minHeight,
        p: { xs: 2, md: 2.75 },
        boxShadow: (theme) => theme.palette.mode === "light" ? "0 10px 35px rgba(32, 54, 44, 0.05)" : "none",
        "&:hover": { borderColor: "primary.main", transform: "translateY(-2px)" },
      }}
    >
      <Stack
        direction="row"
        sx={{ justifyContent: "space-between", alignItems: "center", borderBottom: 1, borderColor: "divider", pb: 2 }}
      >
        <Typography component="h2" variant="subtitle2">{title}</Typography>
        <Typography variant="caption" color="primary.main" sx={{ letterSpacing: ".1em" }}>{meta}</Typography>
      </Stack>
      <Box>{children}</Box>
    </Paper>
  );
}
