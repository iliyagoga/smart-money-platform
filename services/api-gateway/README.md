# API Gateway и Keycloak

Единая защищённая точка входа: `http://localhost:8050/api/v1`.

Маршруты имеют вид `/api/v1/{service}/{upstream-path}`, где `service` — `data`, `smc`, `decision`, `execution` или `analytics`. Например: `GET /api/v1/data/market/candles`.

Keycloak доступен на `http://localhost:8080`, realm — `smart-money`. Для локальной разработки импортируются пользователи `admin`, `trader`, `viewer` с начальным паролем `CHANGE_ME`. Перед любым внешним развёртыванием пользователей и их пароли необходимо заменить; переменные `KEYCLOAK_ADMIN*` относятся только к административной консоли Keycloak.

Получение токена:

```bash
curl -X POST http://localhost:8080/realms/smart-money/protocol/openid-connect/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'client_id=smart-money-api' -d 'grant_type=password' \
  -d 'username=viewer' -d 'password=CHANGE_ME'
```

Роли: `viewer` читает данные, `trader` также выполняет торговые операции, `admin` имеет полный доступ, включая `/internal/*` и изменение risk config.

WebSocket доступен по `/ws`. Для браузера передайте protocols `['access_token', token]`, затем сообщение `{"op":"subscribe","events":["candle.*","position.*"],"symbols":["BTC-USDT-SWAP"]}`. Поддерживаются `unsubscribe` и `ping`.
