# Decision and Risk Service

Принимает сигналы `ELLIOTT_WAVE3`, сохраняет оценку детектора Elliott,
разрешает конфликты и проверяет ограничения риска перед исполнением.
ML, адаптивное переобучение и загрузка моделей отсутствуют.

API: `/risk/config`, `/risk/calculate`, `/internal/scenarios/evaluate`,
`/signals/simulate-elliott`. Порт 8020.
