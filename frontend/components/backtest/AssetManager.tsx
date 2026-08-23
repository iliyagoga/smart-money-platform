"use client";

import { Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { isValidAssetSymbol, normalizeAssetSymbol, useTradingAssets } from "../../hooks/useTradingAssets";

interface AssetManagerProps { selectedAsset: string; onSelect: (asset: string) => void }

export function AssetManager({ onSelect, selectedAsset }: AssetManagerProps) {
  const { assets, addAsset, removeAsset } = useTradingAssets();
  const [isOpen, setIsOpen] = useState(false);
  const [newAsset, setNewAsset] = useState("");
  const normalizedAsset = normalizeAssetSymbol(newAsset);
  const isValid = isValidAssetSymbol(normalizedAsset) && !assets.includes(normalizedAsset);

  const add = () => {
    if (!addAsset(newAsset)) return;
    onSelect(normalizedAsset);
    setNewAsset("");
    setIsOpen(false);
  };

  const remove = (asset: string) => {
    if (assets.length === 1) return;
    removeAsset(asset);
    if (selectedAsset === asset) onSelect(assets.find((item) => item !== asset) ?? assets[0]);
  };

  return <>
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
      {assets.map((asset) => <Chip
        key={asset}
        label={asset}
        color={asset === selectedAsset ? "primary" : "default"}
        variant={asset === selectedAsset ? "filled" : "outlined"}
        onClick={() => onSelect(asset)}
        onDelete={assets.length > 1 ? () => remove(asset) : undefined}
      />)}
      <Button variant="outlined" onClick={() => setIsOpen(true)}>+ Добавить актив</Button>
    </Stack>
    <Dialog open={isOpen} onClose={() => setIsOpen(false)} fullWidth maxWidth="xs">
      <DialogTitle>Добавить торговый актив</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Укажите биржевой символ, например SOL-USDT-SWAP или ETH-USDT.
        </Typography>
        <TextField
          autoFocus
          fullWidth
          label="Символ актива"
          value={newAsset}
          onChange={(event) => setNewAsset(event.target.value)}
          error={Boolean(newAsset) && !isValid}
          helperText={newAsset && !isValid ? "Проверьте формат или актив уже добавлен" : "Формат: BASE-QUOTE-SWAP"}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setIsOpen(false)}>Отмена</Button>
        <Button variant="contained" onClick={add} disabled={!isValid}>Добавить</Button>
      </DialogActions>
    </Dialog>
  </>;
}
