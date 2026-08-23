# Smart Money Service

Событийный Python-сервис анализа рынка. Подписывается на Redis `candle.update` и последовательно выполняет Swing, Trend, Structure (BOS/CHOCH/MSS), Order Block, FVG, Liquidity и Scenario engines.

Активное состояние кешируется в Redis, история объектов записывается в TimescaleDB. События публикуются в `structure.update`, `smc.update` и `scenario.update` в общем envelope-формате.

REST API соответствует разделу Smart Money документации. Для детерминированной загрузки/тестирования также доступен `POST /internal/analyze`.

```bash
docker compose up --build -d smc-service
curl http://localhost:8010/health
```

Тесты:

```bash
pytest -q services/smc-service/tests
```
