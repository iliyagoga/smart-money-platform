import { Box, Button, Paper, Typography } from "@mui/material";

export function SignalPanel() {
  return (
    <Paper
      variant="outlined"
      sx={{
        minHeight: 300,
        p: 2.75,
        position: "relative",
        overflow: "hidden",
        background: (theme) => theme.palette.mode === "light"
          ? "linear-gradient(145deg, #ffffff 30%, #f2f8e8)"
          : "linear-gradient(145deg, #101715 30%, #172018)",
      }}
    >
      <Typography className="eyebrow">SYSTEM SIGNAL</Typography>
      <Typography component="h2" variant="h5" sx={{ my: 2 }}>Анализ рынка<br />и события системы</Typography>
      <Typography variant="body2" color="text.secondary">Проверяйте состояние сервисов и последние события перед запуском операций.</Typography>
      <Button component="a" href="#events" variant="text" sx={{ mt: 2.5, px: 0 }}>Перейти к событиям →</Button>
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
