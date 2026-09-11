# Smart Money Platform — Elliott

Платформа анализирует волны Elliott, выполняет исторические бэктесты и управляет
торговыми конфигурациями, портфелями, ордерами и позициями. ML, обучение моделей
и стандартные SMC-стратегии удалены из рабочего контура.

## Запуск

```bash
cp .env.example .env
docker compose up -d --build --remove-orphans
docker compose ps
```

Frontend: http://localhost:3000. API Gateway: http://localhost:8050.
Keycloak: http://localhost:8080. Realm содержит роли `admin`, `trader`, `viewer`,
но намеренно не импортирует пользователей или пароли. Первого пользователя платформы
создайте через административную консоль Keycloak и назначьте ему роль `admin`.

## Сервисы

| Сервис | Назначение | Порт |
| --- | --- | --- |
| data-service | Закрытые свечи, рыночные данные, PostgreSQL | 8000 |
| elliott-service | Live-паттерны и сигналы Elliott | 8010 |
| decision-service | Отбор сигналов и риск-лимиты | 8020 |
| execution-service | Ордера, позиции, конфигурации и портфели | 8030 |
| analytics-service | Метрики и мониторинг | 8040 |
| api-gateway | Авторизация и маршрутизация REST/WebSocket | 8050 |
| exchange-gateway | Рыночные данные и история OKX | 8070 |
| backtest-service | Исторический replay Elliott | 8085 |

Инфраструктура: PostgreSQL/TimescaleDB, Redis и Keycloak.
PostgreSQL, Redis и прикладные микросервисы не публикуют порты на хост: доступ к ним
идёт только через Docker network. На loopback публикуются frontend, API и Keycloak,
чтобы перед ними можно было безопасно поставить TLS reverse proxy.

## Публичное развёртывание

Не публикуйте порты `3000`, `8050` и `8080` напрямую в интернет. Заполните случайные
`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `KEYCLOAK_ADMIN_PASSWORD`, публичные HTTPS URL
и hostnames из `.env.example`, затем запустите встроенный TLS ingress:

```bash
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d --build
```

DNS-записи `FRONTEND_HOST`, `API_HOST` и `KEYCLOAK_HOST` должны указывать на сервер;
production overlay сам формирует из них HTTPS issuer, CORS allowlist и frontend URL,
а входящие TCP 80/443 — быть открыты для автоматического выпуска сертификатов Caddy.
API в production overlay откажется запускаться с HTTP issuer,
не-HTTPS CORS origin, wildcard Host или дефолтным административным паролем.
Публичный ingress не пропускает Keycloak Admin Console. Для первоначального создания
пользователя откройте SSH tunnel к `127.0.0.1:8080` на сервере и работайте с консолью
через этот tunnel; не меняйте bind address на `0.0.0.0`.

Перед включением `OKX_TRADING_ENABLED` создайте отдельный API key без права вывода
средств, ограничьте его IP-адресом сервера и сначала проверьте DEMO. Любые ключи,
которые когда-либо попадали в логи, терминал или чат, необходимо отозвать и создать заново.

## Работа с платформой

1. В «Конфигурациях» задайте таймфреймы Macro, Structure и Entry, модель входа
   Elliott, ATR/ZigZag, Stop Loss, цели Risk/Reward и параметры риска.
2. В «Бэктесте» выберите актив, загрузите историю OKX для нужных таймфреймов
   и задайте начало и конец тестового периода.
3. Запустите бэктест. Он использует сохранённые закрытые свечи и тот же детектор
   Elliott, что и live-сервис. Обучающего периода и ML-модели нет.
4. Откройте результат: кривая капитала, сделки, просадка, диагностика волн.
   Сохранённые запуски можно сравнить, выгрузить в CSV/JSON и открыть в Replay.
5. В «Рынке» просматривайте паттерны и сигналы активных конфигураций;
   в «Сделках» — ордера, позиции и результаты исполнения.

Бэктест не отправляет ордера на биржу. Режим исполнения задаётся через
`EXECUTION_MODE`; подключение биржевого исполнения — через `OKX_TRADING_ENABLED`.

## Проверки разработки

Frontend (Node.js 22):

```bash
cd frontend
npm ci
npm run check
npm run build
npx playwright install --with-deps chromium
npm run test:ui
```

`test:ui` запускает production-сервер на порту 3100 и проверяет интерфейс в Chromium
на экранах 1920 px и Pixel 7 с тестовыми ответами Keycloak и API.
Полные интеграционные тесты `npm run test:e2e` требуют работающего Docker-окружения;
для загрузки реальных свечей дополнительно задайте `E2E_REAL_BACKTEST=1`.

Для каждого Python-сервиса запускайте тесты в отдельном виртуальном окружении
из каталога сервиса:

```bash
python -m pip install -r requirements.txt pytest==9.1.1 pytest-asyncio==1.4.0
python -m pytest -q
```

Java-сервис проверяется с JDK 21:

```bash
mvn -B -f services/data-service/pom.xml verify
```

CI выполняет lint, TypeScript, unit-тесты, production-сборку, изолированные
браузерные проверки, тесты семи Python-сервисов и сборку с тестами Java-сервиса.
