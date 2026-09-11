# Smart Money Platform — Elliott

Платформа анализирует волны Elliott, выполняет исторические бэктесты и управляет
торговыми конфигурациями, портфелями, ордерами и позициями. ML, обучение моделей
и стандартные SMC-стратегии удалены из рабочего контура.

## Полный локальный запуск

Требуются Docker Engine с Compose и свободные локальные порты `3000`, `8050` и
`8080`. Создайте локальный файл окружения:

```bash
cp .env.example .env
```

Перед запуском обязательно замените значения `CHANGE_ME` для
`POSTGRES_PASSWORD`, `REDIS_PASSWORD` и `KEYCLOAK_ADMIN_PASSWORD`. Для локальной
работы оставьте:

```dotenv
ENVIRONMENT=development
PUBLIC_FRONTEND_URL=http://localhost:3000
PUBLIC_API_URL=http://localhost:8050
PUBLIC_KEYCLOAK_URL=http://localhost:8080
PUBLIC_API_HOSTS=localhost,127.0.0.1
DEPLOYMENT_BIND_ADDRESS=127.0.0.1
```

Проверьте конфигурацию, соберите и запустите весь стек:

```bash
docker compose config --quiet
docker compose up -d --build --remove-orphans
docker compose ps
curl http://localhost:8050/health
```

Дождитесь состояния `healthy` у сервисов. После запуска доступны:

- frontend: http://localhost:3000;
- API Gateway: http://localhost:8050;
- Keycloak: http://localhost:8080;
- Keycloak Admin Console: http://localhost:8080/admin/master/console/.

### Первый пользователь и вход

`KEYCLOAK_ADMIN` и `KEYCLOAK_ADMIN_PASSWORD` создают bootstrap-администратора
realm `master`. Эта учётная запись предназначена только для Keycloak Admin Console
и **не может использоваться для входа во frontend**, который работает с realm
`smart-money`. Bootstrap-переменные применяются при первом создании Keycloak;
последующее редактирование `.env` само по себе пароль существующего администратора
не меняет.

Чтобы создать первого пользователя платформы:

1. Откройте Keycloak Admin Console и войдите значениями `KEYCLOAK_ADMIN` и
   `KEYCLOAK_ADMIN_PASSWORD` из `.env`.
2. В левом верхнем списке realm переключитесь с `master` на `smart-money`.
3. Откройте **Users**, нажмите **Create new user**, задайте username и включите
   пользователя.
4. На вкладке **Credentials** задайте пароль. Отключите **Temporary**, если не
   хотите обязательную смену пароля при первом входе.
5. На вкладке **Role mapping** выберите **Assign role**, включите отображение realm
   roles и назначьте одну или несколько ролей `admin`, `trader`, `viewer`.
6. Выйдите из старой сессии frontend и войдите созданным пользователем на
   http://localhost:3000.

Роли платформы:

- `viewer` — просмотр данных;
- `trader` — управление торговыми конфигурациями, ордерами и позициями;
- `admin` — управление пользователями, risk-настройками и служебными операциями.

Если изменить пароль bootstrap-администратора через Keycloak, обновите
`KEYCLOAK_ADMIN_PASSWORD` в `.env` и пересоздайте API Gateway, иначе управление
пользователями из интерфейса платформы перестанет работать:

```bash
docker compose up -d --force-recreate api-gateway
```

Пользовательские конфигурации и портфели привязаны не к username, а к неизменяемому
Keycloak user ID (`sub`). Не удаляйте пользователя и не пересоздавайте realm, если
за ним уже закреплены данные: новый пользователь с тем же именем получит другой ID
и не увидит старые конфигурации. Обычная смена пароля ID не меняет. Команда
`docker compose down` сохраняет данные, а `docker compose down -v` удаляет volumes
PostgreSQL, Redis и Keycloak — для рабочего окружения её использовать нельзя.

### Остановка и повторный запуск

```bash
docker compose stop
docker compose start
```

Для обновления после изменения исходного кода:

```bash
docker compose up -d --build --remove-orphans
```

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
| backtest-service | Исторический replay Elliott | 8080 |

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

Для OKX Demo заполните `OKX_API_KEY`, `OKX_SECRET_KEY`, `OKX_PASSPHRASE`, оставьте
`OKX_DEMO=true` и установите `OKX_TRADING_ENABLED=true`. После изменения `.env`
пересоздайте exchange gateway:

```bash
docker compose up -d --force-recreate exchange-gateway
curl http://localhost:8050/health
```

В интерфейсе активируйте торговую конфигурацию в режиме `DEMO`. Режим конкретного
актива (`PAPER`, `DEMO` или `PRODUCTION`) хранится в его торговой конфигурации;
`OKX_DEMO` определяет, к какому аккаунту подключён exchange gateway. Конфигурация
`PRODUCTION` не будет принята gateway, запущенным с `OKX_DEMO=true`, и наоборот.

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

Бэктест не отправляет ордера на биржу. `PAPER` исполняется внутри платформы без
биржевой заявки; `DEMO` и `PRODUCTION` отправляются через OKX только при включённом
`OKX_TRADING_ENABLED` и совпадающем значении `OKX_DEMO`.

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
