# Elliott Backtest Service

Replay Elliott по сохранённым закрытым свечам с прогревом индикаторов до
начала теста. Поддерживается только `strategy: ELLIOTT`. Настройки стратегии
задаются в `config.elliott`, период — в `test_from` и `test_to`.

Сервис учитывает комиссии, проскальзывание, funding, объём, размер контракта,
частичные выходы, Stop Loss и Risk/Reward. Результаты и задания сохраняются
в PostgreSQL. API: `/assets`, `/datasets`, `/backtests`, `/backtests/{id}`.
Внешний порт 8085; внутренний — 8080. Обучение и объектное хранилище не используются.
