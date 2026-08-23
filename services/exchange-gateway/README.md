# OKX Exchange Gateway

Единственная точка интеграции с OKX. Публичные `trades`/`books5` читаются из public WebSocket, свечи — из business WebSocket. REST backfill: `POST /exchange/sync`. По умолчанию автоматическое сетевое подключение выключено (`MARKET_DATA_ENABLED=false`), торговый режим — demo.
