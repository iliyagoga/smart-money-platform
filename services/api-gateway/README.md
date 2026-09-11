# API Gateway и Keycloak

Единая защищённая точка входа: `http://localhost:8050/api/v1`.

Маршруты имеют вид `/api/v1/{service}/{upstream-path}`, где `service` — `data`, `elliott`, `decision`, `execution` или `analytics`. Например: `GET /api/v1/data/market/candles`.

Keycloak доступен локально на `http://localhost:8080`, realm — `smart-money`.
Импорт создаёт роли, но не создаёт пользователей с известными паролями. Создайте
первого пользователя в Keycloak Admin Console, назначьте роль `admin`, а остальных
пользователей затем можно администрировать через интерфейс платформы. Password grant
для браузерного клиента отключён; frontend использует Authorization Code + PKCE.

Роли: `viewer` читает данные, `trader` также выполняет торговые операции, `admin` имеет полный доступ, включая `/internal/*` и изменение risk config.

WebSocket доступен по `/ws`. Для браузера передайте protocols `['access_token', token]`, затем сообщение `{"op":"subscribe","events":["candle.*","position.*"],"symbols":["BTC-USDT-SWAP"]}`. Поддерживаются `unsubscribe` и `ping`.
