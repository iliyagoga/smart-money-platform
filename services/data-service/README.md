# Data Service

Сервис приёма и выдачи рыночных данных платформы Elliott Wave. Данные хранятся в TimescaleDB, обновления публикуются через Redis Pub/Sub в формате из `docs/API docs.docx`.

## API

- `GET /market/candles?symbol=BTC-USDT-SWAP&timeframe=M1&limit=500`
- `GET /market/ticks?symbol=BTC-USDT-SWAP&limit=500`
- `GET /market/orderbook?symbol=BTC-USDT-SWAP&depth=10`
- `POST /internal/ingest/candles`
- `POST /internal/ingest/ticks`
- `POST /internal/ingest/orderbook`
- `GET /actuator/health`
- `GET /swagger-ui.html`

Внутренние POST endpoints предназначены для адаптера биржи/API Gateway. Заголовок `X-Correlation-ID` переносится в событие; если его нет, сервис создаёт UUID. Повтор свечи или снимка обновляет запись, повтор тика игнорируется.

## Запуск

Из корня проекта:

```bash
cp .env.example .env
docker compose up --build
```

Пример загрузки свечи:

```bash
curl -X POST http://localhost:8000/internal/ingest/candles \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"BTC-USDT-SWAP","timeframe":"M1","timestamp":1755942000000,"open":65000,"high":65100,"low":64950,"close":65050,"volume":12.5,"is_closed":true}'
```

## Проверка

```bash
mvn test
```
