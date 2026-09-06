# Elliott Wave Service

Live-анализ Эллиотта на закрытых свечах. Детектор и конфигурация импортируются из
`services/backtest-service/src/elliott.py` и `models.py` как `backtest_core`.
Сервис хранит последние 500 свечей каждого актива и таймфрейма.

Контур: свечи → ATR ZigZag → волна 1 → коррекция волны 2 → подтверждение входа в волну 3.
Macro, Structure и Entry — отдельные таймфреймы. Вход, структурный стоп, RR-цели
и фильтры задаются конфигурацией Эллиотта для актива.

Сервис подписан на `candle.update`, сохраняет сигналы `ELLIOTT_WAVE3` в PostgreSQL
и публикует `scenario.created` в `scenario.update`. После рестарта восстанавливает
идентификаторы сигналов для защиты от повторной отправки. Пересчёт истории
через `/internal/rebuild` не создаёт торговых сигналов.

API (порт 8010):

- `GET /health`
- `GET /elliott/patterns?symbol=...`
- `GET /elliott/entries?symbol=...`
- `POST /elliott/history`
- `GET /scenarios`, `GET /scenarios/{id}`
- `POST /internal/analyze`, `POST /internal/rebuild`

Внешний префикс gateway: `/api/v1/elliott`.

## Различие live и бэктеста

Детектор волн общий, но исполнение входов пока различается.
Live явно реализует CHOCH_MARKET, CHOCH_RETRACE и WAVE1_BREAK_RETRACE.
Для остальных моделей текущий live-код использует общий fallback: LIMIT по
текущей цене закрытия. В бэктесте у всех 13 моделей отдельная логика.
Это ограничение существующего live-исполнения, а не детектора волн.
