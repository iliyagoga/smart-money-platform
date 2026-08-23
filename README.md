# Smart Money Platform

Реализованный модуль: [`services/data-service`](services/data-service/README.md) — Java-сервис рыночных данных согласно документации в `docs`.

```bash
cp .env.example .env
docker compose up --build
```

После старта API доступен на `http://localhost:8000`, Swagger UI — на `http://localhost:8000/swagger-ui.html`.

Модули SMC-анализа находятся в [`services/smc-service`](services/smc-service/README.md). API сервиса доступен на `http://localhost:8010`, OpenAPI — на `http://localhost:8010/docs`.

Probability Engine, Conflict Resolver и Risk Manager находятся в [`services/decision-service`](services/decision-service/README.md). API доступен на `http://localhost:8020`.

Paper Order Service, Execution Engine и Position Manager находятся в [`services/execution-service`](services/execution-service/README.md). API доступен на `http://localhost:8030`.

Portfolio Manager, Analytics и Monitoring находятся в [`services/analytics-service`](services/analytics-service/README.md). API доступен на `http://localhost:8040`.

Защищённая внешняя точка входа находится в [`services/api-gateway`](services/api-gateway/README.md). Gateway доступен на `http://localhost:8050`, Keycloak — на `http://localhost:8080`. Внутренние порты сервисов опубликованы только для локальной разработки.

Learning Platform находится в [`services/learning-service`](services/learning-service/README.md). API доступен на `http://localhost:8060`, артефакты моделей сохраняются в MinIO.

Offline-эмулятор и управление торговыми активами находятся в
[`services/backtest-service`](services/backtest-service/README.md). API доступен на `http://localhost:8085`.

Интеграция с OKX находится в [`services/exchange-gateway`](services/exchange-gateway/README.md). Сервис доступен на `http://localhost:8070`; автоматическое подключение к бирже по умолчанию выключено.

Frontend Platform находится в [`frontend`](frontend). Интерфейс доступен на `http://localhost:3000` и использует Keycloak Authorization Code + PKCE.
