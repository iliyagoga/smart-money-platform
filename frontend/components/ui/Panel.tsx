import { Box, Paper, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

interface PanelProps { children: ReactNode; title: string; meta: string; minHeight?: number }

export function Panel({ children, title, meta, minHeight = 300 }: PanelProps) {
  return (
    <Paper variant="outlined" sx={{ minHeight, p: 2.75 }}>
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
