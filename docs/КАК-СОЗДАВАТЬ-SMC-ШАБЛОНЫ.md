# Как создавать шаблоны SMC-стратегий

Шаблон в `config/scenario-templates/*.json` полностью описывает торговый паттерн. Python-движок только обнаруживает базовые объекты рынка и исполняет настройки шаблона. Пустой `template_ids` в бэктесте означает: проверить все шаблоны с `enabled: true`.

## Последовательность анализа

1. `timeframe_roles.context` задаёт ТФ первичной структуры.
2. `context_structure_types` задаёт допустимые события направления: `BOS`, `CHOCH`, `MSS`.
3. `timeframe_roles.zones` задаёт ТФ зон интереса (OB/FVG).
4. `timeframe_roles.triggers` задаёт ТФ подтверждения и исполнения.
5. `required_objects` и `relations` определяют состав паттерна.
6. Правила `entry_rule`, `stop_rule`, `target_rule` формируют торговый план.
7. При нескольких одновременных сценариях выбирается больший `priority`, затем больший `confidence`.

Это соответствует top-down подходу из статей: первичная структура на старших ТФ, вторичная структура и точка входа на младших; ликвидность, OB и imbalance используются как отдельные настраиваемые подтверждения.

## Поля шаблона

- `id`, `name`, `version`, `enabled` — идентификация и управление миграцией. При изменении системного шаблона обязательно увеличьте `version`.
- `sources` — ссылки на статьи или исследования, из которых взята логика шаблона.
- `draft_notes` — допущения и ограничения черновика. Для черновика задавайте `enabled: false`, пока он не проверен на графике и бэктесте.
- `priority` — целое число 0–100. Это единственный источник приоритета паттерна.
- `timeframe_roles.context/zones/triggers` — распределение ролей по ТФ.
- `require_context` — требовать ли структуру на context-ТФ.
- `context_structure_types` — какие структурные события формируют направление.
- `direction_source` — источник стороны сделки: `CONTEXT`, `ORDER_BLOCK` или `FVG`.
- `required_objects` — требуемые `ORDER_BLOCK` и/или `FVG`; `min_strength` задаёт минимальную силу.
- `relations` — дополнительные связи: `OB_OVERLAPS_FVG`, `LIQUIDITY_SWEPT`, `LIQUIDITY_IN_DIRECTION`, `STRUCTURE_BOS`, `STRUCTURE_CHOCH_OR_MSS`, `OB_RETESTED`, `PREMIUM_DISCOUNT`, `HIGHER_TIMEFRAME_ALIGNMENT`.
- `require_zone_touch` — создавать сценарий только после касания зоны trigger-свечой.
- `require_confirmation`, `confirmation_types`, `confirmation_window_bars` — обязательность, типы и временное окно локального подтверждения.
- `require_liquidity_sweep` — требовать SFP/sweep ликвидности в направлении разворота.
- `entry_rule` — `ORDER_BLOCK`, `FVG`, `OB_FVG_INTERSECTION`, `FIFTY_PERCENT` (вход на 0.5 зоны) или `OTE` (0.62–0.79 зоны).
- `stop_rule` — `ORDER_BLOCK_EDGE`, `LAST_SWING` или `TRIGGER_WICK`.
- `stop_atr_buffer` — буфер за структурной границей, в долях ширины зоны.
- `target_rule` — `FIXED_RR` или `LIQUIDITY_THEN_RR`; `risk_reward` содержит RR-цели.
- `ttl_minutes` — срок жизни сценария.
- `base_confidence`, `context_bonus`, `confirmation_bonus`, `sweep_bonus`, `overlap_bonus`, `strength_weight` — полностью настраиваемая формула confidence.

## Пример: SFP-разворот от Order Block

```json
{
  "id": "SFP_OB_REVERSAL",
  "name": "SFP-разворот от старшего OB",
  "version": 1,
  "enabled": true,
  "priority": 95,
  "timeframe_roles": {
    "context": ["D1", "H4"],
    "zones": ["H1", "M30"],
    "triggers": ["M15", "M5"]
  },
  "require_context": true,
  "context_structure_types": ["CHOCH", "MSS", "BOS"],
  "direction_source": "CONTEXT",
  "required_objects": [{"kind": "ORDER_BLOCK", "min_strength": 0.4}],
  "relations": ["LIQUIDITY_SWEPT"],
  "require_zone_touch": true,
  "require_confirmation": true,
  "confirmation_types": ["CHOCH", "MSS"],
  "confirmation_window_bars": 6,
  "require_liquidity_sweep": true,
  "entry_rule": "FIFTY_PERCENT",
  "stop_rule": "TRIGGER_WICK",
  "stop_atr_buffer": 0.1,
  "target_rule": "LIQUIDITY_THEN_RR",
  "risk_reward": [2, 3],
  "ttl_minutes": 240,
  "base_confidence": 0.55,
  "context_bonus": 0.05,
  "confirmation_bonus": 0.1,
  "sweep_bonus": 0.1,
  "overlap_bonus": 0,
  "strength_weight": 0.1
}
```

## Проверка нового шаблона

1. Проверьте JSON и увеличьте `version` при изменении встроенного шаблона.
2. Запустите тесты SMC и backtest service.
3. Запустите бэктест с пустым `template_ids`.
4. На графике SMC-разметки проверьте зону, entry, SL, TP и маркеры сделок.
5. В «Диагностике поиска паттернов» проверьте причины отсева (`NO_CONTEXT_STRUCTURE`, `NO_ZONE_TOUCH`, `NO_TRIGGER_CONFIRMATION`, `NO_LIQUIDITY_SWEEP`). Большое число отказов — повод менять конкретный шаблон, а не код движка.

Шаблон не должен обещать доходность. Любое изменение проверяется на непересекающихся train/test-периодах и на нескольких рыночных режимах.
