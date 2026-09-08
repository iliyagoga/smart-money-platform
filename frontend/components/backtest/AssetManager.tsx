"use client";

import { Alert, Button, Chip, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from "@mui/material";
import { useState } from "react";
import { isValidAssetSymbol, normalizeAssetSymbol, useTradingAssets } from "../../hooks/useTradingAssets";
import { useAuth } from "../auth/AuthProvider";

interface AssetManagerProps {
  addAsset?: (value: string) => Promise<boolean>;
  assets?: string[];
  onAssetsChanged?: () => void;
  onSelect: (asset: string) => void;
  removeAsset?: (asset: string) => Promise<void>;
  selectedAsset: string;
}

export function AssetManager(props: AssetManagerProps) {
  const resource = useTradingAssets();
  const assets = props.assets ?? resource.assets;
  const addAsset = props.addAsset ?? resource.addAsset;
  const removeAsset = props.removeAsset ?? resource.removeAsset;
  const { onAssetsChanged, onSelect, selectedAsset } = props;
  const { roles } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [newAsset, setNewAsset] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const normalizedAsset = normalizeAssetSymbol(newAsset);
  const isValid = isValidAssetSymbol(normalizedAsset) && !assets.includes(normalizedAsset);
  const canManage = roles.includes("admin");

  const add = async () => {
    setIsSaving(true);
    setError("");
    try {
      if (!await addAsset(newAsset)) return;
      onSelect(normalizedAsset);
      onAssetsChanged?.();
      setNewAsset("");
      setIsOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsSaving(false);
    }
  };

  const remove = async (asset: string) => {
    if (assets.length === 1) return;
    try {
      await removeAsset(asset);
      onAssetsChanged?.();
      if (selectedAsset === asset) onSelect(assets.find((item) => item !== asset) ?? assets[0]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return <>
    <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: "wrap", alignItems: "center" }}>
      {assets.map((asset) => <Chip
        key={asset}
        label={asset}
        color={asset === selectedAsset ? "primary" : "default"}
        variant={asset === selectedAsset ? "filled" : "outlined"}
        onClick={() => onSelect(asset)}
        onDelete={canManage && assets.length > 1 ? () => void remove(asset) : undefined}
      />)}
      <Button variant="outlined" onClick={() => setIsOpen(true)} disabled={!canManage}>+ Добавить актив</Button>
    </Stack>
    {error && !isOpen && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
    <Dialog open={isOpen} onClose={() => !isSaving && setIsOpen(false)} maxWidth="md">
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
        {error && <Typography variant="caption" color="error.main">{error}</Typography>}
      </DialogContent>
      <DialogActions>
        <Button disabled={isSaving} onClick={() => setIsOpen(false)}>Отмена</Button>
        <Button variant="contained" onClick={() => void add()} disabled={!isValid || isSaving}>
          {isSaving ? "Добавляем…" : "Добавить"}
        </Button>
      </DialogActions>
    </Dialog>
  </>;
}
