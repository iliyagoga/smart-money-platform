# Smart Money Service

Событийный Python-сервис анализа рынка. Подписывается на Redis `candle.update` и последовательно выполняет Swing, Trend, Structure (BOS/CHOCH/MSS), Order Block, FVG, Liquidity и Scenario engines.

Активное состояние кешируется в Redis, история объектов записывается в TimescaleDB. События публикуются в `structure.update`, `smc.update` и `scenario.update` в общем envelope-формате.

REST API соответствует разделу Smart Money документации. Для детерминированной загрузки/тестирования также доступен `POST /internal/analyze`.

## Шаблоны сценариев

Шаблоны не зашиты в Python. Исходные JSON-файлы находятся в `config/scenario-templates`, а рабочая библиотека хранится в общем Docker
volume `scenario_templates`. Scenario Manager перечитывает включённые шаблоны при каждом анализе структуры.

- `GET /scenario-templates` — список и чтение;
- `GET /scenario-templates/{id}` — один шаблон;
- `PUT /scenario-templates/{id}` — создать или атомарно обновить JSON;
- `DELETE /scenario-templates/{id}` — удалить.

Изменение и удаление через API Gateway разрешено только роли `admin`. JSON валидируется до сохранения.

```bash
docker compose up --build -d smc-service
curl http://localhost:8010/health
```

Тесты:

```bash
pytest -q services/smc-service/tests
```
