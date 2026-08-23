# OKX Exchange Gateway

Единственная точка интеграции с OKX. Публичные `trades`/`books5` читаются из public WebSocket, свечи — из business WebSocket. REST backfill: `POST /exchange/sync`. По умолчанию автоматическое сетевое подключение выключено (`MARKET_DATA_ENABLED=false`), торговый режим — demo.

## Исторические свечи

`POST /exchange/history` создаёт фоновую задачу. Для каждого ТФ сервис запрашивает официальный OKX endpoint
`/api/v5/market/history-candles` страницами по 300 записей, двигается назад через курсор `after` и пакетно сохраняет только закрытые свечи.

```json
{
  "symbol": "BTC-USDT-SWAP",
  "timeframes": ["M1", "M5", "M15", "H1", "H4", "D1"],
  "from_timestamp": 1735689600000,
  "to_timestamp": 1787529599000,
  "max_candles_per_timeframe": 100000
}
```

Статус: `GET /exchange/history/{job_id}`. Повторная загрузка безопасна: ключ свечи состоит из символа, ТФ и времени, сохранение использует
upsert. Через API Gateway запуск разрешён только администратору.
