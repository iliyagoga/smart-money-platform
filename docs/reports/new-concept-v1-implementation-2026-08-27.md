# New Concept v1 — детерминированная SMC-система

## Архитектура

```text
closed candle
→ Swing/Trend/Structure
→ BOS или CHOCH
→ structural Order Block + FVG
→ fixed AlgorithmEngine
→ AlgorithmSignal
→ deterministic Risk Manager
→ Execution Service
```

Scenario Manager, генерация сценариев, relations/event sequence, Probability Engine, Conflict Resolver, bandit, Kelly sizing, local retraining и learning-service удалены.

## Входная конфигурация

`config/algorithm-configs/DEMO_SMC_V1.json` содержит только параметры встроенного алгоритма:

- execution timeframes и направления;
- источник входа OB/FVG;
- full/body границы OB;
- минимальная сила OB и displacement в ATR;
- минимальный FVG в ATR;
- volume period/ratio;
- ADX period/minimum;
- ATR buffer стопа;
- RR, allocations, срок входа и one-trade-per-zone.

JSON не задаёт исполняемую последовательность и не создаёт новые типы торговой логики.

## SMC v1

- подтверждённые фракталы нормализуются в чередующуюся Swing-цепочку;
- consecutive Swing одного типа заменяется более сильным экстремумом;
- BOS/CHOCH хранит ID пробитого Swing и displacement;
- OB создаётся только из структурного break и последней противоположной свечи импульсной ноги;
- OB получает body/full boundaries, displacement, volume ratio и strength score;
- FVG хранит размер в ATR, displacement, CE 50% и максимальную глубину заполнения;
- liquidity pool расположен на Swing, ATR используется для equal-high/low tolerance;
- ADX рассчитывается внутри общего ядра без ML.

## Совместимость

Экран бэктеста, график зон, сделки, комиссии, slippage, funding, partial take profit, break-even и liquidation сохранены. В ответе replay временно остаётся ключ `scenarios`, потому что его читает существующий frontend; содержимое ключа является прямым отображением `AlgorithmSignal`.

Endpoint `/scenario-templates` также временно сохранён как frontend-совместимый alias списка `AlgorithmConfig`. Новые нативные live-сигналы доступны через `/signals` и Redis `signal.update`.

## Проверки

- сборка production frontend;
- сборка smc, backtest, decision, execution и api-gateway контейнеров;
- SMC tests: 5 passed;
- backtest tests: 10 passed;
- decision tests: 4 passed;
- execution tests: 5 passed;
- API gateway tests: 8 passed;
- сервисы запущены и healthy;
- восстановленная рыночная история создала реальные `DEMO_SMC_V1` AlgorithmSignal.

## Ограничения первой версии

- структура пока однотаймфреймовая внутри каждого сигнала; HTF context не является обязательным;
- режим митигации присутствует в конфигурации, но точное close-inside/full lifecycle требует следующей итерации исполнения;
- ADX реализован простым rolling Wilder-style расчётом;
- UI и JSON-ответ бэктеста используют часть старых имён для совместимости;
- перед подбором параметров нужен длительный out-of-sample backtest и визуальная проверка разметки.
