# Decision and Risk Service

Содержит Probability Engine, Conflict Resolver и Risk Manager.

- принимает `scenario.created` из Redis Pub/Sub;
- рассчитывает ансамблевый confidence;
- разрешает конфликт LONG/SHORT по порогу и минимальной разнице;
- создаёт `TradeSignal`;
- проверяет дневной убыток и число позиций;
- рассчитывает размер позиции по ограниченному дробному Kelly;
- записывает `signal.created` и `risk.approved/rejected` в Redis Stream `trading.command`;
- сохраняет журнал решений и риск-проверок в PostgreSQL.

REST API: `/probability/calculate`, `/risk/config`, `/risk/calculate`. OpenAPI доступен на `/docs`.

```bash
docker compose up --build -d decision-service
curl http://localhost:8020/health
```
