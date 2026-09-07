# Elliott Service

Live-анализ волн Elliott на закрытых свечах. Сервис использует детектор
`services/backtest-service/src/elliott.py`, хранит историю свечей в памяти,
восстанавливает её из PostgreSQL и публикует сигналы в Redis.

API: `GET /elliott/patterns`, `GET /elliott/entries`, `POST /elliott/history`;
внутренние операции: `POST /internal/analyze`, `POST /internal/rebuild`.
Порт 8010. SMC-движков и редактора шаблонов нет.
