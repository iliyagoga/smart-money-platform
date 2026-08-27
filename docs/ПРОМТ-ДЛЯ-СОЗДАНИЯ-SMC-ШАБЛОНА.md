# Промт для создания SMC-шаблона другой нейросетью

Скопируйте весь текст ниже в другую нейросеть. В секцию «Исходный материал» вставьте текст статьи, конспект или ссылки и при необходимости заполните пожелания.

---

Ты — системный аналитик алгоритмических торговых стратегий и специалист по формализации Smart Money Concepts. Твоя задача — преобразовать предоставленный материал в один строгий JSON-шаблон для существующего Scenario Manager. Не придумывай торговые правила, которых нет в источнике. Не обещай доходность и не подгоняй параметры под желаемый результат.

## Исходный материал

Вставь сюда статью, конспект или описание стратегии:

Ссылки на источники, если они есть:

```text
https://smart-money.trading/smart-money-concept/
https://smart-money.trading/ready-to-use-smart-money-strategy/
```

Дополнительные пожелания пользователя:

```text
[ИНСТРУМЕНТ, СТИЛЬ ТОРГОВЛИ, НУЖНЫЕ ТАЙМФРЕЙМЫ, LONG/SHORT И ДРУГИЕ ОГРАНИЧЕНИЯ]
```

## Цель

Создай один практически проверяемый шаблон торгового сценария. Он должен описывать:

1. контекст и направление на старшем таймфрейме;
2. таймфрейм поиска зоны интереса;
3. триггерный таймфрейм;
4. необходимые Order Block, FVG, ликвидность и структуру;
5. последовательность событий до входа;
6. правило зоны и точки входа;
7. структурный Stop Loss;
8. цели и минимальное отношение прибыль/риск;
9. частичное закрытие и перенос Stop Loss;
10. срок действия сигнала, повторные входы и cooldown.

## Жёсткие ограничения формата

- Ответ должен содержать только один валидный JSON-объект без Markdown, комментариев и пояснений.
- Не добавляй поле `enabled`: в системе его больше нет.
- Не добавляй неизвестные поля.
- Не используй Python, JavaScript, формулы в строках или произвольные условия: движок поддерживает только перечисленные ниже значения.
- `id` должен соответствовать `^[A-Z][A-Z0-9_]+$`, быть содержательным и уникальным.
- Для нового шаблона используй `version: 1`.
- Поддерживаемые таймфреймы: `M1`, `M5`, `M15`, `M30`, `H1`, `H4`, `D1`.
- Все обязательные решения должны быть выражены полями JSON, а не только текстом в `draft_notes`.
- Если источник не определяет важный параметр, выбери консервативное значение и явно запиши допущение в `draft_notes`.
- Если материал принципиально невозможно выразить этой схемой, всё равно верни валидный максимально близкий шаблон и перечисли невыразимые ограничения в `draft_notes`. Не изобретай новые enum-значения.

## Допустимая схема

### Идентификация

- `id`: строка в верхнем регистре с `_`.
- `name`: понятное русское название.
- `version`: целое число от 1.
- `sources`: массив реальных URL из исходного материала. Не выдумывай URL.
- `draft_notes`: массив коротких строк с допущениями, неоднозначностями и ограничениями реализации.
- `priority`: целое число 0–100. При одновременных сигналах выше приоритет у большего значения.

### Роли таймфреймов

Поле `timeframe_roles` обязательно для top-down шаблона:

```json
{
  "context": ["D1"],
  "zones": ["H1"],
  "triggers": ["M5"]
}
```

- `context` — таймфреймы структуры и направления.
- `zones` — таймфреймы Order Block/FVG.
- `triggers` — таймфреймы подтверждения и исполнения.
- Каждый массив должен содержать хотя бы один таймфрейм.
- `primary_context_timeframe`, если задан, обязан входить в `timeframe_roles.context`.
- `allowed_timeframes` укажи полным объединением таймфреймов, на которых шаблон разрешён.

### Контекст и направление

- `context_structure_types`: только `BOS`, `CHOCH`, `MSS`.
- `direction_source`: только `CONTEXT`, `ORDER_BLOCK` или `FVG`.
- `allowed_directions`: непустой массив из `LONG`, `SHORT`.
- `require_context`: нужно ли обязательное структурное событие на context-ТФ.
- `context_alignment_mode`:
  - `ANY` — без строгого согласования всех context-ТФ;
  - `ALL` — все context-ТФ должны совпадать с направлением;
  - `PRIMARY_ONLY` — направление подтверждает главный context-ТФ;
  - `PRIMARY_WITHOUT_CONFLICT` — главный ТФ совпадает, остальные не должны быть направлены против сделки.
- `minimum_context_alignments`: целое 1–7; применяется при связи `HIGHER_TIMEFRAME_ALIGNMENT`.

### Объекты и связи

`required_objects` — непустой массив объектов следующего вида:

```json
{
  "kind": "ORDER_BLOCK",
  "active": true,
  "same_direction": true,
  "min_strength": 0.5
}
```

- `kind`: используй только `ORDER_BLOCK` и/или `FVG`.
- `active` и `same_direction`: boolean.
- `min_strength`: число 0–1.

`relations` может содержать только:

- `OB_OVERLAPS_FVG`;
- `LIQUIDITY_IN_DIRECTION`;
- `LIQUIDITY_SWEPT`;
- `STRUCTURE_BOS`;
- `STRUCTURE_CHOCH_OR_MSS`;
- `OB_RETESTED`;
- `PREMIUM_DISCOUNT`;
- `HIGHER_TIMEFRAME_ALIGNMENT`.

Не дублируй элементы массива.

### Подтверждение и порядок событий

- `require_zone_touch`: требовать касание зоны trigger-свечой.
- `require_confirmation`: требовать локальное подтверждение.
- `confirmation_types`: массив только из `BOS`, `CHOCH`, `MSS`.
- `confirmation_window_bars`: целое 1–100.
- `require_liquidity_sweep`: требовать снятие ликвидности.
- `event_sequence`: уникальная последовательность только из `LIQUIDITY_SWEEP`, `CONFIRMATION`, `ZONE_TOUCH`.
- Включай событие в `event_sequence` только тогда, когда соответствующее условие действительно обязательно.
- `zone_created_before_confirmation`: должна ли зона существовать до подтверждения.
- `minimum_zone_retests`: целое 0–100.
- `maximum_zone_retests`: `null` или целое не меньше `minimum_zone_retests`.
- `maximum_zone_age_bars`: `null` или целое 1–10000.

### Вход

`entry_rule` допускает только:

- `ORDER_BLOCK` — зона входа по OB;
- `FVG` — зона входа по FVG;
- `OB_FVG_INTERSECTION` — пересечение OB и FVG;
- `FIFTY_PERCENT` — середина зоны;
- `OTE` — область 0.62–0.79 зоны.

Выбранное правило должно соответствовать `required_objects`. Например, для `OB_FVG_INTERSECTION` потребуй и `ORDER_BLOCK`, и `FVG`, а также обычно добавь `OB_OVERLAPS_FVG`.

### Stop Loss

`stop_rule` допускает только:

- `ORDER_BLOCK_EDGE` — за дальней границей Order Block;
- `LAST_SWING` — за последним Swing Low для Long или Swing High для Short;
- `TRIGGER_WICK` — за экстремумом trigger-свечи; при sweep учитывается экстремум снятой ликвидности.

Дополнительные поля:

- `stop_atr_buffer`: число 0–10; фактически это доля ширины зоны, добавляемая за структурную границу. Не называй её настоящим ATR в пояснениях.
- `minimum_stop_percent`: `null` или число больше 0 и не более 20.
- `maximum_stop_percent`: `null` или число больше 0 и не более 20.
- Если обе границы заданы, минимум не должен превышать максимум.
- Сценарий с дистанцией стопа вне диапазона будет отклонён, а не искусственно подогнан.

### Take Profit и RR

`target_rule` допускает только:

- `FIXED_RR` — цели только по заданным коэффициентам RR;
- `LIQUIDITY_THEN_RR` — цель по доступной ликвидности плюс резервные RR-цели;
- `NEXT_ORDER_BLOCK` — цель по следующему противоположному Order Block.

Дополнительные поля:

- `risk_reward`: непустой массив положительных RR, например `[2, 3]`.
- `minimum_target_rr`: `null` или положительное число.
- `maximum_target_rr`: `null` или положительное число больше `minimum_target_rr`.
- `target_allocations`: либо пустой массив, либо столько же положительных долей, сколько элементов в `risk_reward`; сумма строго равна 1.
- Для структурной SMC-стратегии без иных требований предпочитай минимум `2R`, но пометь это как допущение, если источник не задаёт RR.

### Сопровождение позиции

- `break_even_rule`:
  - `NEVER` — не переносить стоп автоматически;
  - `ONE_R` — переносить стоп в цену входа после прохождения 1R;
  - `AFTER_TARGET` — переносить после указанной цели.
- `move_stop_to_break_even_after_target`: `null` или номер цели от 1; нужен при `AFTER_TARGET`.
- `one_trade_per_zone`: запрещает повторный вход по тому же Order Block.
- `cooldown_bars_after_stop`: целое 0–10000.
- `entry_valid_for_bars`: `null` или целое 1–10000; предпочтительнее для срока жизни в свечах trigger-ТФ.
- `ttl_minutes`: целое от 1; используется как временной срок жизни, если точное окно в свечах не задано.

### Confidence

Все значения — числа 0–1:

- `base_confidence`;
- `context_bonus`;
- `confirmation_bonus`;
- `sweep_bonus`;
- `overlap_bonus`;
- `strength_weight`.

Итог ограничивается сверху значением 0.99. Не завышай коэффициенты без основания в источнике.

## Логика принятия решений

Перед формированием ответа мысленно выполни следующие шаги:

1. Отдели прямые правила источника от своих допущений.
2. Определи, является стратегия продолжением или разворотом.
3. Определи источник направления и главный context-ТФ.
4. Назначь отдельные роли context, zones и triggers.
5. Выбери минимально необходимый набор объектов и связей — не добавляй конфлюэнсы «для качества», если их нет в источнике.
6. Проверь, что требования sweep, confirmation и zone touch согласованы с `event_sequence`.
7. Проверь соответствие `entry_rule` требуемым объектам.
8. Выбери структурный `stop_rule`, не заменяй его произвольным фиксированным процентом.
9. Выбери `target_rule`, RR и распределение позиции.
10. Проверь, что Long и Short логически зеркальны, если разрешены обе стороны.
11. Проверь все enum, диапазоны, массивы и суммы.
12. Запиши каждое вынужденное допущение в `draft_notes`.

## Обязательный каркас результата

Заполни все поля каркаса конкретными значениями. Удалять поля нельзя; для необязательных ограничений используй `null` или пустой массив там, где это разрешено.

```json
{
  "id": "UNIQUE_TEMPLATE_ID",
  "name": "Название стратегии",
  "version": 1,
  "sources": [],
  "draft_notes": [],
  "priority": 80,
  "allowed_timeframes": ["D1", "H4", "H1", "M15", "M5"],
  "timeframe_roles": {
    "context": ["D1", "H4"],
    "zones": ["H1"],
    "triggers": ["M15", "M5"]
  },
  "primary_context_timeframe": "D1",
  "context_alignment_mode": "PRIMARY_WITHOUT_CONFLICT",
  "context_structure_types": ["BOS", "CHOCH", "MSS"],
  "direction_source": "CONTEXT",
  "allowed_directions": ["LONG", "SHORT"],
  "minimum_context_alignments": 1,
  "required_objects": [
    {
      "kind": "ORDER_BLOCK",
      "active": true,
      "same_direction": true,
      "min_strength": 0.5
    }
  ],
  "relations": [],
  "require_context": true,
  "require_zone_touch": true,
  "require_confirmation": true,
  "confirmation_types": ["CHOCH", "MSS"],
  "require_liquidity_sweep": true,
  "confirmation_window_bars": 12,
  "event_sequence": ["LIQUIDITY_SWEEP", "CONFIRMATION", "ZONE_TOUCH"],
  "zone_created_before_confirmation": true,
  "minimum_zone_retests": 0,
  "maximum_zone_retests": 2,
  "maximum_zone_age_bars": 40,
  "entry_rule": "ORDER_BLOCK",
  "stop_rule": "LAST_SWING",
  "stop_atr_buffer": 0.1,
  "minimum_stop_percent": null,
  "maximum_stop_percent": null,
  "target_rule": "LIQUIDITY_THEN_RR",
  "risk_reward": [2, 3],
  "minimum_target_rr": 2,
  "maximum_target_rr": 8,
  "target_allocations": [0.6, 0.4],
  "break_even_rule": "AFTER_TARGET",
  "move_stop_to_break_even_after_target": 1,
  "ttl_minutes": 1440,
  "entry_valid_for_bars": 8,
  "one_trade_per_zone": true,
  "cooldown_bars_after_stop": 12,
  "base_confidence": 0.55,
  "overlap_bonus": 0,
  "strength_weight": 0.1,
  "context_bonus": 0.08,
  "confirmation_bonus": 0.1,
  "sweep_bonus": 0.12
}
```

## Финальная самопроверка

Перед ответом убедись:

- JSON синтаксически валиден;
- присутствует ровно один корневой объект;
- поля `enabled` нет;
- неизвестных полей и enum нет;
- `id` соответствует формату;
- все таймфреймы поддерживаются;
- `primary_context_timeframe` входит в context;
- обязательные массивы не пусты;
- события не повторяются;
- минимумы не превышают максимумы;
- сумма `target_allocations` равна 1;
- число `target_allocations` равно числу `risk_reward`;
- правила входа, стопа и целей не противоречат требуемым объектам;
- допущения перечислены в `draft_notes`;
- ответ содержит только JSON.

Теперь верни только итоговый JSON-объект.

---
