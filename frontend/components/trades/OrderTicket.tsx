"use client";

import { Alert, Button, Grid, MenuItem, Paper, TextField, Typography } from "@mui/material";
import { useState } from "react";
import type { FormEvent } from "react";
import { useTradingAssets } from "../../hooks/useTradingAssets";
import type { OrderDraft } from "../../lib/types";

interface OrderTicketProps {
  canTrade: boolean;
  isSubmitting: boolean;
  onSubmit: (order: OrderDraft) => void;
}

export function OrderTicket({ canTrade, isSubmitting, onSubmit }: OrderTicketProps) {
  const { assets } = useTradingAssets();
  const [symbol, setSymbol] = useState(assets[0]);
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [type, setType] = useState<"MARKET" | "LIMIT" | "STOP">("MARKET");
  const [price, setPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const selectedSymbol = assets.includes(symbol) ? symbol : assets[0];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const parsedQuantity = Number(quantity);
    const parsedPrice = Number(price);
    if (!parsedQuantity || (type !== "MARKET" && !parsedPrice)) return;
    onSubmit({
      symbol: selectedSymbol,
      side,
      type,
      quantity: parsedQuantity,
      price: type === "MARKET" ? undefined : parsedPrice,
      stop_loss_price: stopLoss ? Number(stopLoss) : undefined,
      take_profit_prices: takeProfit ? [Number(takeProfit)] : [],
    });
  };

  return (
    <Paper component="form" onSubmit={submit} variant="outlined" sx={{ p: { xs: 2, md: 2.5 } }}>
      <Typography variant="h6">Новый paper-ордер</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>Ордер исполняется только в тестовом контуре.</Typography>
      {!canTrade && <Alert severity="info" sx={{ mb: 2 }}>Для создания ордеров необходима роль trader или admin.</Alert>}
      <Grid container spacing={1.5}>
        <Grid size={{ xs: 12, md: 4 }}>
          <TextField
            select
            fullWidth
            label="Инструмент"
            value={selectedSymbol}
            onChange={(event) => setSymbol(event.target.value)}
            disabled={!canTrade}
          >
            {assets.map((item) => <MenuItem key={item} value={item}>{item}</MenuItem>)}
          </TextField>
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <TextField
            select
            fullWidth
            label="Сторона"
            value={side}
            onChange={(event) => setSide(event.target.value as "BUY" | "SELL")}
            disabled={!canTrade}
          >
            <MenuItem value="BUY">BUY</MenuItem><MenuItem value="SELL">SELL</MenuItem>
          </TextField>
        </Grid>
        <Grid size={{ xs: 6, md: 2 }}>
          <TextField
            select
            fullWidth
            label="Тип"
            value={type}
            onChange={(event) => setType(event.target.value as typeof type)}
            disabled={!canTrade}
          >
            <MenuItem value="MARKET">Market</MenuItem><MenuItem value="LIMIT">Limit</MenuItem><MenuItem value="STOP">Stop</MenuItem>
          </TextField>
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}><TextField fullWidth label="Количество" value={quantity} onChange={(event) => setQuantity(event.target.value)} type="number"
          required disabled={!canTrade} slotProps={{ htmlInput: { min: 0, step: "any" } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 2 }}><TextField fullWidth label="Цена" value={price} onChange={(event) => setPrice(event.target.value)} type="number"
          required={type !== "MARKET"} disabled={!canTrade || type === "MARKET"}
          slotProps={{ htmlInput: { min: 0, step: "any" } }} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <TextField fullWidth label="Stop Loss" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)}
            type="number" disabled={!canTrade} />
        </Grid>
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <TextField fullWidth label="Take Profit" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)}
            type="number" disabled={!canTrade} />
        </Grid>
        <Grid size={{ xs: 12, md: 6 }}><Button fullWidth type="submit" variant="contained" color={side === "BUY" ? "success" : "error"}
          disabled={!canTrade || isSubmitting || Number(quantity) <= 0 || (type !== "MARKET" && Number(price) <= 0)}>
          {isSubmitting ? "Отправляем…" : `${side} ${selectedSymbol}`}
        </Button></Grid>
      </Grid>
    </Paper>
  );
}
