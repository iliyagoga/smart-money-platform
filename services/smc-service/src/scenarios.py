from __future__ import annotations

import json
import os
import shutil
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


class TimeframeRoles(BaseModel):
    """Timeframes on which a setup builds context, a POI and an entry trigger."""
    context: list[Timeframe] = [Timeframe.D1, Timeframe.H4]
    zones: list[Timeframe] = [Timeframe.H1, Timeframe.M30]
    triggers: list[Timeframe] = [Timeframe.M5, Timeframe.M1]


class ScenarioTemplate(BaseModel):
    id: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    name: str
    version: int = Field(default=1, ge=1)
    enabled: bool = True
    required_objects: list[ObjectRule]
    relations: list[str] = []
    allowed_timeframes: list[Timeframe] = list(Timeframe)
    timeframe_roles: TimeframeRoles | None = None
    priority: int = Field(default=50, ge=0, le=100)
    context_structure_types: list[str] = ["BOS"]
    require_context: bool = True
    require_zone_touch: bool = True
    require_confirmation: bool = True
    confirmation_types: list[str] = ["CHOCH", "MSS"]
    require_liquidity_sweep: bool = False
    confirmation_window_bars: int = Field(default=6, ge=1, le=100)
    direction_source: str = "CONTEXT"
    entry_rule: str = "OB_FVG_INTERSECTION"
    stop_rule: str = "ORDER_BLOCK_EDGE"
    stop_atr_buffer: float = Field(default=.1, ge=0, le=10)
    target_rule: str = "LIQUIDITY_THEN_RR"
    risk_reward: list[float] = [2, 3]
    ttl_minutes: int = Field(default=1440, ge=1)
    base_confidence: float = Field(default=.5, ge=0, le=1)
    overlap_bonus: float = Field(default=.1, ge=0, le=1)
    strength_weight: float = Field(default=.1, ge=0, le=1)
    context_bonus: float = Field(default=.04, ge=0, le=1)
    confirmation_bonus: float = Field(default=.04, ge=0, le=1)
    sweep_bonus: float = Field(default=.05, ge=0, le=1)

    @model_validator(mode="after")
    def validate_rules(self):
        supported = {
            "relations": {
                "OB_OVERLAPS_FVG", "LIQUIDITY_IN_DIRECTION", "LIQUIDITY_SWEPT", "STRUCTURE_BOS",
                "STRUCTURE_CHOCH_OR_MSS", "OB_RETESTED", "PREMIUM_DISCOUNT", "HIGHER_TIMEFRAME_ALIGNMENT",
            },
            "entry_rule": {"OB_FVG_INTERSECTION", "ORDER_BLOCK", "FVG", "FIFTY_PERCENT", "OTE"},
            "stop_rule": {"ORDER_BLOCK_EDGE", "LAST_SWING", "TRIGGER_WICK"},
            "target_rule": {"LIQUIDITY_THEN_RR", "FIXED_RR", "NEXT_ORDER_BLOCK"},
        }
        if any(item not in supported["relations"] for item in self.relations):
            raise ValueError("unsupported relation")
        if any(item not in {"BOS", "CHOCH", "MSS"} for item in self.confirmation_types):
            raise ValueError("unsupported confirmation type")
        if any(item not in {"BOS", "CHOCH", "MSS"} for item in self.context_structure_types):
            raise ValueError("unsupported context structure type")
        if self.timeframe_roles:
            roles = self.timeframe_roles
            if not roles.context or not roles.zones or not roles.triggers:
                raise ValueError("timeframe roles cannot be empty")
        for field in ("entry_rule", "stop_rule", "target_rule"):
            if getattr(self, field) not in supported[field]:
                raise ValueError(f"unsupported {field}")
        if self.direction_source not in {"CONTEXT", "ORDER_BLOCK", "FVG"}:
            raise ValueError("unsupported direction source")
        return self


class TemplateStore:
    def __init__(self, directory: str | Path | None = None):
        configured = directory or os.getenv("SCENARIO_TEMPLATE_DIR", "/app/scenario-templates")
        self.directory = Path(configured)
        self.directory.mkdir(parents=True, exist_ok=True)
        defaults = Path(os.getenv("DEFAULT_SCENARIO_TEMPLATE_DIR", ""))
        if defaults.is_dir():
            for source in defaults.glob("*.json"):
                destination = self.directory / source.name
                source_data = json.loads(source.read_text(encoding="utf-8"))
                destination_version = 0
                if destination.exists():
                    try:
                        destination_version = json.loads(destination.read_text(encoding="utf-8")).get("version", 0)
                    except (OSError, ValueError, TypeError):
                        destination_version = 0
                if not destination.exists() or source_data.get("version", 1) > destination_version:
                    shutil.copyfile(source, destination)

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
        self.diagnostics: dict[str, dict[str, int]] = {}

    def generate(self, symbol, timeframe, obs, fvgs, liquidity, template_ids=None, now=None,
                 changes=None, swings=None, trends=None):
        created = []
        timestamp = now or int(time() * 1000)
        templates = sorted(self.store.list(enabled_only=True), key=lambda item: (-item.priority, item.id))
        for template in templates:
            if template_ids and template.id not in template_ids:
                continue
            if timeframe not in template.allowed_timeframes:
                continue
            created.extend(self._evaluate(
                template, symbol, timeframe, obs, fvgs, liquidity, timestamp,
                changes or [], swings or [], trends or [],
            ))
        return created

    def generate_top_down(self, symbol, candle, pipeline, template_ids=None):
        """Evaluate every template using its configured timeframe roles."""
        created = []
        for template in self.store.list(enabled_only=True):
            if template_ids and template.id not in template_ids:
                continue
            roles = template.timeframe_roles
            if roles is None or candle.timeframe not in roles.triggers:
                continue
            created.extend(self._evaluate_timeframe_template(template, symbol, candle, pipeline))
        return created

    def _reject(self, template_id: str, reason: str):
        counters = self.diagnostics.setdefault(template_id, {})
        counters[reason] = counters.get(reason, 0) + 1

    def _evaluate_timeframe_template(self, template, symbol, candle, pipeline):
        roles = template.timeframe_roles
        context_keys = [(symbol, item) for item in roles.context]
        zone_keys = [(symbol, item) for item in roles.zones]
        trigger_key = (symbol, candle.timeframe)
        context = [item for key in context_keys for item in pipeline.changes[key]
                   if item.type in template.context_structure_types and item.timestamp <= candle.timestamp]
        if template.require_context and not context:
            self._reject(template.id, "NO_CONTEXT_STRUCTURE")
            return []
        bias = max(context, key=lambda item: item.timestamp) if context else None
        bias_direction = bias.direction if bias else None
        ob_rule = next((rule for rule in template.required_objects if rule.kind == "ORDER_BLOCK"), None)
        fvg_rule = next((rule for rule in template.required_objects if rule.kind == "FVG"), None)
        obs = [item for key in zone_keys for item in pipeline.obs[key]
               if not item.is_broken and (bias_direction is None or item.type == bias_direction)
               and (not ob_rule or item.strength_score >= ob_rule.min_strength)]
        fvgs = [item for key in zone_keys for item in pipeline.fvgs[key]
                if not item.is_filled and (bias_direction is None or item.type == bias_direction)]
        touched_obs = [item for item in obs if candle.low <= item.zone_high and candle.high >= item.zone_low]
        touched_fvgs = [item for item in fvgs if candle.low <= item.zone_high and candle.high >= item.zone_low]
        if ob_rule and not (touched_obs if template.require_zone_touch else obs):
            self._reject(template.id, "NO_ZONE_TOUCH")
            return []
        if fvg_rule and not (touched_fvgs if template.require_zone_touch else fvgs):
            self._reject(template.id, "NO_FVG_TOUCH")
            return []
        candidate_obs = touched_obs if template.require_zone_touch else obs
        candidate_fvgs = touched_fvgs if template.require_zone_touch else fvgs
        ob = candidate_obs[0] if candidate_obs else None
        fvg = next((gap for gap in candidate_fvgs if not ob or gap.zone_low <= ob.zone_high and gap.zone_high >= ob.zone_low), None)
        if "OB_OVERLAPS_FVG" in template.relations and (not ob or not fvg):
            self._reject(template.id, "NO_OB_FVG_OVERLAP")
            return []
        if "OB_RETESTED" in template.relations and (not ob or ob.retest_count < 1):
            self._reject(template.id, "NO_OB_RETEST")
            return []
        interval = {Timeframe.M1: 60_000, Timeframe.M5: 300_000, Timeframe.M15: 900_000,
                    Timeframe.M30: 1_800_000, Timeframe.H1: 3_600_000,
                    Timeframe.H4: 14_400_000, Timeframe.D1: 86_400_000}[candle.timeframe]
        cutoff = candle.timestamp - template.confirmation_window_bars * interval
        source = bias_direction if template.direction_source == "CONTEXT" else ob.type if template.direction_source == "ORDER_BLOCK" and ob else fvg.type if fvg else bias_direction
        if source is None:
            self._reject(template.id, "NO_DIRECTION_SOURCE")
            return []
        direction = "LONG" if source == Direction.BULLISH else "SHORT"
        confirmations = [item for item in pipeline.changes[trigger_key]
                         if item.direction == source and item.type in template.confirmation_types
                         and cutoff <= item.timestamp <= candle.timestamp]
        if template.require_confirmation and not confirmations:
            self._reject(template.id, "NO_TRIGGER_CONFIRMATION")
            return []
        confirmation = confirmations[-1] if confirmations else None
        if "STRUCTURE_BOS" in template.relations and not any(item.type == "BOS" for item in confirmations):
            self._reject(template.id, "NO_TRIGGER_BOS")
            return []
        if "STRUCTURE_CHOCH_OR_MSS" in template.relations and not any(
            item.type in {"CHOCH", "MSS"} for item in confirmations
        ):
            self._reject(template.id, "NO_TRIGGER_CHOCH_MSS")
            return []
        sweep_type = "SELL_STOP" if direction == "LONG" else "BUY_STOP"
        sweeps = [item for item in pipeline.liquidity[trigger_key]
                  if item.swept and item.type == sweep_type and cutoff <= item.created_at <= candle.timestamp]
        requires_sweep = template.require_liquidity_sweep or "LIQUIDITY_SWEPT" in template.relations
        if requires_sweep and not sweeps:
            self._reject(template.id, "NO_LIQUIDITY_SWEEP")
            return []
        sweep = sweeps[-1] if sweeps else None
        if template.entry_rule == "FVG" and fvg:
            zone_low, zone_high = fvg.zone_low, fvg.zone_high
        elif template.entry_rule == "ORDER_BLOCK" and ob:
            zone_low, zone_high = ob.zone_low, ob.zone_high
        else:
            zone_low = max(item.zone_low for item in (ob, fvg) if item) if ob and fvg else (ob or fvg).zone_low
            zone_high = min(item.zone_high for item in (ob, fvg) if item) if ob and fvg else (ob or fvg).zone_high
        if template.entry_rule == "FIFTY_PERCENT":
            zone_low = zone_high = (zone_low + zone_high) / 2
        elif template.entry_rule == "OTE":
            origin_low, origin_high = zone_low, zone_high
            zone_low = origin_low + (origin_high - origin_low) * .62
            zone_high = origin_low + (origin_high - origin_low) * .79
        entry = (zone_low + zone_high) / 2
        if "PREMIUM_DISCOUNT" in template.relations:
            structural_prices = [item.price for key in zone_keys for item in pipeline.swings[key]][-40:]
            if structural_prices:
                equilibrium = (min(structural_prices) + max(structural_prices)) / 2
                if direction == "LONG" and entry > equilibrium or direction == "SHORT" and entry < equilibrium:
                    self._reject(template.id, "WRONG_PREMIUM_DISCOUNT")
                    return []
        if "HIGHER_TIMEFRAME_ALIGNMENT" in template.relations:
            trends = [pipeline.trends.get(key) for key in context_keys]
            aligned = [item for item in trends if item and (
                direction == "LONG" and item.direction == "UP" or direction == "SHORT" and item.direction == "DOWN"
            )]
            if len(aligned) < 2:
                self._reject(template.id, "NO_HTF_ALIGNMENT")
                return []
        stop_anchor = zone_low if direction == "LONG" else zone_high
        if template.stop_rule == "TRIGGER_WICK":
            stop_anchor = candle.low if direction == "LONG" else candle.high
        elif template.stop_rule == "LAST_SWING":
            wanted = "LOW" if direction == "LONG" else "HIGH"
            structural = [item for item in pipeline.swings[trigger_key] if item.type == wanted]
            if structural:
                stop_anchor = structural[-1].price
        if sweep and template.stop_rule == "TRIGGER_WICK":
            stop_anchor = min(stop_anchor, sweep.price_level) if direction == "LONG" else max(stop_anchor, sweep.price_level)
        width = max(zone_high - zone_low, entry * .0001)
        stop = stop_anchor - width * template.stop_atr_buffer if direction == "LONG" else stop_anchor + width * template.stop_atr_buffer
        risk = max(abs(entry - stop), entry * .0001)
        target_liquidity = [item.price_level for key in context_keys + zone_keys for item in pipeline.liquidity[key]
                            if not item.swept and ((direction == "LONG" and item.type == "BUY_STOP" and item.price_level > entry)
                            or (direction == "SHORT" and item.type == "SELL_STOP" and item.price_level < entry))]
        if "LIQUIDITY_IN_DIRECTION" in template.relations and not target_liquidity:
            self._reject(template.id, "NO_TARGET_LIQUIDITY")
            return []
        targets = [] if template.target_rule == "FIXED_RR" else sorted(set(target_liquidity), reverse=direction == "SHORT")[:2]
        if template.target_rule == "NEXT_ORDER_BLOCK":
            targets = sorted({(item.zone_low + item.zone_high) / 2 for key in zone_keys for item in pipeline.obs[key]
                              if not item.is_broken and item.type != source and (
                              direction == "LONG" and item.zone_low > entry or direction == "SHORT" and item.zone_high < entry)},
                             reverse=direction == "SHORT")[:2]
        if template.target_rule in {"FIXED_RR", "LIQUIDITY_THEN_RR"}:
            targets.extend(entry + risk * rr * (1 if direction == "LONG" else -1) for rr in template.risk_reward)
        targets = list(dict.fromkeys(targets))[:max(1, len(template.risk_reward))]
        object_ids = [item.id for item in (bias, confirmation, ob, fvg, sweep) if item]
        scenario_id = str(uuid5(NAMESPACE_URL, f"{template.id}:{':'.join(object_ids)}"))
        if scenario_id in self.items:
            self._reject(template.id, "DUPLICATE")
            return []
        confidence = min(.99, template.base_confidence + (template.context_bonus if bias else 0)
                         + (template.confirmation_bonus if confirmation else 0)
                         + (template.overlap_bonus if fvg else 0)
                         + (template.strength_weight * ob.strength_score if ob else 0)
                         + (template.sweep_bonus if sweep else 0))
        scenario = Scenario(
            id=scenario_id, symbol=symbol, timeframe=candle.timeframe, direction=direction,
            setup_type=template.id, priority=template.priority, confidence=confidence, entry_zone_low=zone_low,
            entry_zone_high=zone_high, stop_loss_price=stop, take_profit_prices=targets,
            created_at=candle.timestamp, expires_at=candle.timestamp + template.ttl_minutes * 60_000,
            reasons=[template.name, f"Контекст: {','.join(map(str, roles.context))}",
                     f"Зона: {','.join(map(str, roles.zones))}", f"Триггер: {candle.timeframe}"],
            objects_used=([{"type": "CONTEXT_STRUCTURE", "id": bias.id}] if bias else [])
            + ([{"type": "CONFIRMATION", "id": confirmation.id}] if confirmation else [])
            + ([{"type": "ORDER_BLOCK", "id": ob.id}] if ob else [])
            + ([{"type": "FVG", "id": fvg.id}] if fvg else [])
            + ([{"type": "LIQUIDITY_SWEEP", "id": sweep.id}] if sweep else []),
        )
        self.items[scenario_id] = scenario
        return [scenario]

    def _evaluate(self, template, symbol, timeframe, obs, fvgs, liquidity, timestamp, changes, swings, trends):
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
            matching_changes = [item for item in changes if item.direction == ob.type]
            if "STRUCTURE_BOS" in template.relations and not any(item.type == "BOS" for item in matching_changes):
                continue
            if "STRUCTURE_CHOCH_OR_MSS" in template.relations and not any(
                item.type in {"CHOCH", "MSS"} for item in matching_changes
            ):
                continue
            if "OB_RETESTED" in template.relations and ob.retest_count < 1:
                continue
            if "LIQUIDITY_SWEPT" in template.relations and not any(item.swept for item in liquidity):
                continue
            aligned = [
                item for item in trends
                if (direction == "LONG" and item.direction == "UP") or (direction == "SHORT" and item.direction == "DOWN")
            ]
            if "HIGHER_TIMEFRAME_ALIGNMENT" in template.relations and len(aligned) < 2:
                continue
            entry_low = max(ob.zone_low, fvg.zone_low) if fvg else ob.zone_low
            entry_high = min(ob.zone_high, fvg.zone_high) if fvg else ob.zone_high
            if template.entry_rule == "OTE":
                entry_low = ob.zone_low + (ob.zone_high - ob.zone_low) * .62
                entry_high = ob.zone_low + (ob.zone_high - ob.zone_low) * .79
            width = max(ob.zone_high - ob.zone_low, 1e-12)
            stop = ob.zone_low - template.stop_atr_buffer * width if direction == "LONG" else ob.zone_high + template.stop_atr_buffer * width
            directional_swings = [
                item for item in swings
                if (direction == "LONG" and item.type == "LOW") or (direction == "SHORT" and item.type == "HIGH")
            ]
            if template.stop_rule == "LAST_SWING" and directional_swings:
                stop = directional_swings[-1].price
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
            if "PREMIUM_DISCOUNT" in template.relations and swings:
                prices = [item.price for item in swings[-20:]]
                equilibrium = (min(prices) + max(prices)) / 2
                if direction == "LONG" and entry_low > equilibrium or direction == "SHORT" and entry_high < equilibrium:
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
