import { Stack, Typography } from "@mui/material";

export function EmptyState({ text }: { text: string }) {
  return (
    <Stack sx={{ height: 210, alignItems: "center", justifyContent: "center", color: "text.secondary" }}>
      <Typography sx={{ fontSize: 24 }}>◇</Typography>
      <Typography>{text}</Typography>
    </Stack>
  );
}
