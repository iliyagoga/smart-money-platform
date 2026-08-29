"use client";

import { Button, Chip, Paper, Stack, Typography } from "@mui/material";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";

interface TimeframeDataset {
  candles: number;
  from_timestamp: number;
  timeframe: string;
  to_timestamp: number;
}

interface AssetDataset { symbol: string; timeframes: TimeframeDataset[] }

interface DatasetOverviewProps {
  assets: string[];
  canManage: boolean;
  selectedAsset?: string;
}

const date = (timestamp?: number) => timestamp ? new Date(timestamp).toLocaleDateString("ru-RU") : "—";

export function DatasetOverview({ assets, canManage, selectedAsset }: DatasetOverviewProps) {
  const [datasets, setDatasets] = useState<AssetDataset[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const loaded = await Promise.all(assets.map((symbol) => api<AssetDataset>(
        `/api/v1/backtest/datasets/${encodeURIComponent(symbol)}`,
      )));
      setDatasets(loaded);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setIsLoading(false);
    }
  }, [assets]);

  useEffect(() => { void load(); }, [load]);

  const remove = async (symbol: string, timeframe?: string) => {
    const target = timeframe ? `${symbol} · ${timeframe}` : symbol;
    if (!window.confirm(`Удалить все сохранённые свечи ${target}? История бэктестов останется.`)) return;
    setError("");
    try {
      const query = timeframe ? `?timeframe=${encodeURIComponent(timeframe)}` : "";
      await api(`/api/v1/backtest/datasets/${encodeURIComponent(symbol)}${query}`, { method: "DELETE" });
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    }
  };

  return <Paper variant="outlined" sx={{ p: 1.5, my: 1.5 }}>
    <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 1 }}>
      <Typography variant="h6">Загруженные датасеты</Typography>
      <Button size="small" onClick={() => void load()} disabled={isLoading}>
        {isLoading ? "Обновляем…" : "Обновить"}
      </Button>
    </Stack>
    <Stack spacing={0.75}>
      {datasets.map((dataset) => {
        const total = dataset.timeframes.reduce((sum, item) => sum + item.candles, 0);
        return <Paper key={dataset.symbol} variant="outlined" sx={{
          p: 1,
          borderColor: dataset.symbol === selectedAsset ? "primary.main" : "divider",
        }}>
          <Stack direction={{ xs: "column", md: "row" }} sx={{ justifyContent: "space-between", gap: 1 }}>
            <Stack>
              <Typography sx={{ fontWeight: 700 }}>{dataset.symbol}</Typography>
              <Typography variant="caption" color="text.secondary">
                Сумма по всем ТФ: {total.toLocaleString("ru-RU")} свечей
              </Typography>
              {canManage && total > 0 && <Button color="error" size="small" sx={{ alignSelf: "flex-start", mt: 0.5 }}
                onClick={() => void remove(dataset.symbol)}>Удалить датасет</Button>}
            </Stack>
            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.75 }}>
              {dataset.timeframes.length ? dataset.timeframes.map((item) => <Chip
                key={item.timeframe}
                size="small"
                label={`${item.timeframe}: ${item.candles.toLocaleString("ru-RU")} · ${date(item.from_timestamp)} — ${date(item.to_timestamp)}`}
                onDelete={canManage ? () => void remove(dataset.symbol,item.timeframe) : undefined}
              />) : <Chip size="small" label="Нет свечей" color="warning" />}
            </Stack>
          </Stack>
        </Paper>;
      })}
    </Stack>
    {error && <Typography color="error.main" variant="caption">{error}</Typography>}
  </Paper>;
}
