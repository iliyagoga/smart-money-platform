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
  selectedAsset?: string;
}

const date = (timestamp?: number) => timestamp ? new Date(timestamp).toLocaleDateString("ru-RU") : "—";

export function DatasetOverview({ assets, selectedAsset }: DatasetOverviewProps) {
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

  return <Paper variant="outlined" sx={{ p: 2.5, my: 2 }}>
    <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between", mb: 2 }}>
      <Typography variant="h6">Загруженные датасеты</Typography>
      <Button size="small" onClick={() => void load()} disabled={isLoading}>
        {isLoading ? "Обновляем…" : "Обновить"}
      </Button>
    </Stack>
    <Stack spacing={1.5}>
      {datasets.map((dataset) => {
        const total = dataset.timeframes.reduce((sum, item) => sum + item.candles, 0);
        const first = Math.min(...dataset.timeframes.map((item) => item.from_timestamp));
        const last = Math.max(...dataset.timeframes.map((item) => item.to_timestamp));
        return <Paper key={dataset.symbol} variant="outlined" sx={{
          p: 2,
          borderColor: dataset.symbol === selectedAsset ? "primary.main" : "divider",
        }}>
          <Stack direction={{ xs: "column", md: "row" }} sx={{ justifyContent: "space-between", gap: 1 }}>
            <Stack>
              <Typography sx={{ fontWeight: 700 }}>{dataset.symbol}</Typography>
              <Typography variant="caption" color="text.secondary">
                Всего {total.toLocaleString("ru-RU")} · {total ? `${date(first)} — ${date(last)}` : "данных пока нет"}
              </Typography>
            </Stack>
            <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", gap: 0.75 }}>
              {dataset.timeframes.length ? dataset.timeframes.map((item) => <Chip
                key={item.timeframe}
                size="small"
                label={`${item.timeframe}: ${item.candles.toLocaleString("ru-RU")}`}
                title={`${date(item.from_timestamp)} — ${date(item.to_timestamp)}`}
              />) : <Chip size="small" label="Нет свечей" color="warning" />}
            </Stack>
          </Stack>
        </Paper>;
      })}
    </Stack>
    {error && <Typography color="error.main" variant="caption">{error}</Typography>}
  </Paper>;
}
