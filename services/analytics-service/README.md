# Portfolio, Analytics and Monitoring Service

Сервис восстанавливает портфель из закрытых сделок, поддерживает equity и дневной PnL в Redis для Risk Manager, формирует торговые метрики и сохраняет Pub/Sub-события в TimescaleDB Event Store.

API:

- `/portfolio`, `/portfolio/balance`, `/portfolio/equity`, `/portfolio/statistics`
- `/analytics/dashboard`, `/analytics/performance`, `/analytics/winrate`
- `/analytics/profit-factor`, `/analytics/drawdown`, `/analytics/sharpe`
- `/monitoring`, `/monitoring/services`, `/monitoring/events`, `/monitoring/performance`

OpenAPI: `http://localhost:8040/docs`.
