import { Box } from "@mui/material";

export function StatusDot({ active }: { active: boolean }) {
  return (
    <Box
      component="span"
      sx={{
        width: 7,
        height: 7,
        borderRadius: "50%",
        bgcolor: active ? "success.main" : "text.disabled",
        boxShadow: active ? "0 0 8px currentColor" : "none",
        color: "success.main",
      }}
    />
  );
}
