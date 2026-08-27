# Decision and Risk Service

Детерминированный слой риска и передачи ордеров. Сервис принимает `algorithm.signal` из Redis `signal.update`, преобразует его в исполнимый `TradeSignal`, применяет фиксированные лимиты риска и публикует `signal.created` и `risk.approved/rejected` в stream `trading.command`.

В сервисе нет ML, probability engine, bandit, confidence threshold и выбора сценариев. Размер позиции определяется фиксированным процентом риска, расстоянием до Stop Loss и защитными лимитами портфеля.

REST API: `/risk/config`, `/risk/calculate`, `/internal/signals/evaluate`.
