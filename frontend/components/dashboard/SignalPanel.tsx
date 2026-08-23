import { Box, Paper, Typography } from "@mui/material";

export function SignalPanel() {
  return (
    <Paper variant="outlined" sx={{ minHeight: 300, p: 2.75, position: "relative", overflow: "hidden" }}>
      <Typography className="eyebrow">SYSTEM SIGNAL</Typography>
      <Typography component="h2" variant="h5" sx={{ my: 2 }}>Контур готов<br />к анализу рынка</Typography>
      <Typography variant="body2" color="text.secondary">Данные, SMC и риск-сервисы подключены.</Typography>
      <Box
        sx={{
          position: "absolute",
          width: 150,
          height: 150,
          border: 1,
          borderColor: "primary.main",
          borderRadius: "50%",
          right: -40,
          bottom: -45,
        }}
      />
    </Paper>
  );
}
