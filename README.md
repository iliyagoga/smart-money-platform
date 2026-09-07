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
Keycloak: http://localhost:8080. Локальные роли: `admin`, `trader`, `viewer`;
начальный пароль импортируемых пользователей — `CHANGE_ME`.

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
python -m pip install -r requirements.txt
python -m pytest -q
```

Java-сервис проверяется с JDK 21:

```bash
mvn -B -f services/data-service/pom.xml verify
```

CI выполняет lint, TypeScript, unit-тесты, production-сборку, изолированные
браузерные проверки, тесты семи Python-сервисов и сборку с тестами Java-сервиса.
