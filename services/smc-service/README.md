# Smart Money Service

Событийный детерминированный анализатор рынка:

```text
closed candle → Swing/structure → BOS/CHOCH → structural OB/FVG → AlgorithmEngine → AlgorithmSignal
```

Встроенная последовательность находится в коде. JSON из `config/algorithm-configs` является только входной конфигурацией параметров: таймфреймы, направления, режим границ OB, ATR/volume/ADX-пороги, вход, Stop Loss, RR и срок действия.

Произвольных relations, event sequence, генерации сценариев и ML нет. Сигналы публикуются как `algorithm.signal` в Redis `signal.update` и сохраняются в `algorithm_signals`.

Основные API: `/smart-money/*`, `/signals`, `/scenario-templates`. Старое имя `/scenario-templates` временно сохранено для совместимости фронтенда; endpoint возвращает `AlgorithmConfig`.
