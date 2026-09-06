# Decision and Risk Service

Обрабатывает сигналы Эллиотта: Conflict Resolver и Risk Manager.

- принимает `scenario.created` из Redis Pub/Sub;
- сохраняет confidence детектора Эллиотта без обучения и ансамблевых оценок;
- разрешает конфликт LONG/SHORT по порогу и минимальной разнице;
- создаёт `TradeSignal`;
- проверяет дневной убыток и число позиций;
- рассчитывает размер позиции по ограниченному дробному Kelly;
- записывает `signal.created` и `risk.approved/rejected` в Redis Stream `trading.command`;
- сохраняет журнал решений и риск-проверок в PostgreSQL.

REST API: `/risk/config`, `/risk/calculate`. OpenAPI доступен на `/docs`.

```bash
docker compose up --build -d decision-service
curl http://localhost:8020/health
```
