from __future__ import annotations

import json
import os
from pathlib import Path
from time import time
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field, model_validator

from .models import Direction, FVG, LiquidityZone, OrderBlock, Scenario, Timeframe


class ObjectRule(BaseModel):
    kind: str
    active: bool = True
    same_direction: bool = True
    min_strength: float = Field(default=0, ge=0, le=1)


class ScenarioTemplate(BaseModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    name: str
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    required_objects: list[ObjectRule]
    relations: list[str] = []
    allowed_timeframes: list[Timeframe] = list(Timeframe)
    direction_source: str = "ORDER_BLOCK"
    entry_rule: str = "OB_FVG_INTERSECTION"
    stop_rule: str = "ORDER_BLOCK_EDGE"
    stop_atr_buffer: float = Field(default=.1, ge=0, le=10)
    target_rule: str = "LIQUIDITY_THEN_RR"
    risk_reward: list[float] = [2, 3]
    ttl_minutes: int = Field(default=1440, ge=1)
    base_confidence: float = Field(default=.5, ge=0, le=1)
    overlap_bonus: float = Field(default=.1, ge=0, le=1)
    strength_weight: float = Field(default=.1, ge=0, le=1)

    @model_validator(mode="after")
    def validate_rules(self):
        supported = {
            "relations": {"OB_OVERLAPS_FVG", "LIQUIDITY_IN_DIRECTION"},
            "entry_rule": {"OB_FVG_INTERSECTION", "ORDER_BLOCK"},
            "stop_rule": {"ORDER_BLOCK_EDGE"},
            "target_rule": {"LIQUIDITY_THEN_RR", "FIXED_RR"},
        }
        if any(item not in supported["relations"] for item in self.relations):
            raise ValueError("unsupported relation")
        for field in ("entry_rule", "stop_rule", "target_rule"):
            if getattr(self, field) not in supported[field]:
                raise ValueError(f"unsupported {field}")
        return self


class TemplateStore:
    def __init__(self, directory: str | Path | None = None):
        configured = directory or os.getenv("SCENARIO_TEMPLATE_DIR", "/app/scenario-templates")
        self.directory = Path(configured)
        self.directory.mkdir(parents=True, exist_ok=True)

    def list(self, enabled_only: bool = False) -> list[ScenarioTemplate]:
        templates = [self._read(path) for path in sorted(self.directory.glob("*.json"))]
        return [item for item in templates if item.enabled or not enabled_only]

    def get(self, template_id: str) -> ScenarioTemplate | None:
        path = self._path(template_id)
        return self._read(path) if path.exists() else None

    def save(self, template: ScenarioTemplate) -> ScenarioTemplate:
        path = self._path(template.id)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(template.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)
        return template

    def delete(self, template_id: str) -> bool:
        path = self._path(template_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _path(self, template_id: str) -> Path:
        normalized = template_id.strip().upper()
        if not normalized.replace("_", "").isalnum():
            raise ValueError("invalid template id")
        return self.directory / f"{normalized}.json"

    @staticmethod
    def _read(path: Path) -> ScenarioTemplate:
        return ScenarioTemplate.model_validate(json.loads(path.read_text(encoding="utf-8")))


class ScenarioManager:
    def __init__(self, store: TemplateStore | None = None):
        self.items: dict[str, Scenario] = {}
        self.store = store or TemplateStore()

    def generate(self, symbol, timeframe, obs, fvgs, liquidity, template_ids=None, now=None):
        created = []
        timestamp = now or int(time() * 1000)
        for template in self.store.list(enabled_only=True):
            if template_ids and template.id not in template_ids:
                continue
            if timeframe not in template.allowed_timeframes:
                continue
            created.extend(self._evaluate(template, symbol, timeframe, obs, fvgs, liquidity, timestamp))
        return created

    def _evaluate(self, template, symbol, timeframe, obs, fvgs, liquidity, timestamp):
        created = []
        for ob in (item for item in obs if not item.is_broken):
            ob_rule = next((rule for rule in template.required_objects if rule.kind == "ORDER_BLOCK"), None)
            if ob_rule and ob.strength_score < ob_rule.min_strength:
                continue
            overlaps = [
                item for item in fvgs
                if not item.is_filled and item.type == ob.type
                and item.zone_low <= ob.zone_high and item.zone_high >= ob.zone_low
            ]
            if "OB_OVERLAPS_FVG" in template.relations and not overlaps:
                continue
            fvg = overlaps[0] if overlaps else None
            direction = "LONG" if ob.type == Direction.BULLISH else "SHORT"
            entry_low = max(ob.zone_low, fvg.zone_low) if fvg else ob.zone_low
            entry_high = min(ob.zone_high, fvg.zone_high) if fvg else ob.zone_high
            width = max(ob.zone_high - ob.zone_low, 1e-12)
            stop = ob.zone_low - template.stop_atr_buffer * width if direction == "LONG" else ob.zone_high + template.stop_atr_buffer * width
            entry = (entry_low + entry_high) / 2
            risk = abs(entry - stop)
            matching = [
                item for item in liquidity
                if not item.swept and (
                    direction == "LONG" and item.type == "BUY_STOP" and item.price_level > entry
                    or direction == "SHORT" and item.type == "SELL_STOP" and item.price_level < entry
                )
            ]
            if "LIQUIDITY_IN_DIRECTION" in template.relations and not matching:
                continue
            targets = sorted((item.price_level for item in matching), reverse=direction == "SHORT")[:2]
            targets.extend(entry + risk * ratio * (1 if direction == "LONG" else -1) for ratio in template.risk_reward)
            targets = list(dict.fromkeys(targets))[:max(1, len(template.risk_reward))]
            confidence = min(
                .99,
                template.base_confidence + template.overlap_bonus * len(overlaps) + template.strength_weight * ob.strength_score,
            )
            object_ids = [ob.id] + ([fvg.id] if fvg else [])
            scenario_id = str(uuid5(NAMESPACE_URL, f"{template.id}:{':'.join(object_ids)}"))
            if scenario_id in self.items:
                continue
            scenario = Scenario(
                id=scenario_id, symbol=symbol, timeframe=timeframe, direction=direction,
                setup_type=template.id, confidence=confidence, entry_zone_low=entry_low,
                entry_zone_high=entry_high, stop_loss_price=stop, take_profit_prices=targets,
                reasons=[template.name], objects_used=[{"type": "OB", "id": ob.id}]
                + ([{"type": "FVG", "id": fvg.id}] if fvg else []), created_at=timestamp,
                expires_at=timestamp + template.ttl_minutes * 60_000,
            )
            self.items[scenario_id] = scenario
            created.append(scenario)
        return created

    def list(self, symbol=None, status=None):
        now = int(time() * 1000)
        for item in self.items.values():
            if item.status == "ACTIVE" and item.expires_at < now:
                item.status = "EXPIRED"
        return [
            item for item in self.items.values()
            if (not symbol or item.symbol == symbol.upper()) and (not status or item.status == status)
        ]
