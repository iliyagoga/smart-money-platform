import json

import pytest

from collections import defaultdict
from types import SimpleNamespace

from src.models import Candle, Direction, LiquidityZone, OrderBlock, StructureChange, Timeframe
from src.scenarios import ScenarioManager, ScenarioTemplate, TemplateStore


def template():
    return ScenarioTemplate.model_validate({
        "id": "TEST_TEMPLATE",
        "name": "Test",
        "required_objects": [{"kind": "ORDER_BLOCK"}],
        "relations": ["OB_OVERLAPS_FVG"],
    })


def test_template_store_roundtrip(tmp_path):
    store = TemplateStore(tmp_path)
    saved = store.save(template())
    assert saved.id == "TEST_TEMPLATE"
    assert store.get("test_template").name == "Test"
    assert json.loads((tmp_path / "TEST_TEMPLATE.json").read_text())["enabled"] is True
    assert store.delete("TEST_TEMPLATE") is True


def test_unknown_rule_is_rejected():
    with pytest.raises(ValueError):
        ScenarioTemplate.model_validate({
            "id": "INVALID_TEMPLATE",
            "name": "Invalid",
            "required_objects": [],
            "relations": ["PYTHON_EXPRESSION"],
        })


def test_top_down_requires_htf_zone_sweep_and_ltf_confirmation(tmp_path):
    symbol = "BTC-USDT-SWAP"
    pipeline = SimpleNamespace(changes=defaultdict(list), obs=defaultdict(list),
                               fvgs=defaultdict(list), liquidity=defaultdict(list))
    pipeline.changes[(symbol, Timeframe.D1)].append(StructureChange(
        symbol=symbol, timeframe=Timeframe.D1, type="BOS", direction=Direction.BULLISH,
        break_level_price=110, timestamp=1,
    ))
    zone = OrderBlock(symbol=symbol, timeframe=Timeframe.H1, type=Direction.BULLISH,
                      zone_low=99, zone_high=101, created_at=2)
    pipeline.obs[(symbol, Timeframe.H1)].append(zone)
    sweep = LiquidityZone(symbol=symbol, timeframe=Timeframe.M5, type="SELL_STOP",
                          price_level=98, swept=True, created_at=3)
    pipeline.liquidity[(symbol, Timeframe.M5)].append(sweep)
    pipeline.liquidity[(symbol, Timeframe.D1)].append(LiquidityZone(
        symbol=symbol, timeframe=Timeframe.D1, type="BUY_STOP", price_level=120, created_at=1,
    ))
    candle = Candle(symbol=symbol, timeframe=Timeframe.M5, timestamp=4, open=99, high=102,
                    low=97, close=101, volume=1)
    store = TemplateStore(tmp_path)
    store.save(ScenarioTemplate.model_validate({
        "id": "SWEEP_REVERSAL", "name": "Sweep reversal",
            "required_objects": [{"kind": "ORDER_BLOCK"}],
            "timeframe_roles": {"context": ["D1"], "zones": ["H1"], "triggers": ["M5"]},
            "confirmation_types": ["CHOCH", "MSS"], "require_liquidity_sweep": True,
            "stop_rule": "TRIGGER_WICK",
        }))
    manager = ScenarioManager(store)
    assert manager.generate_top_down(symbol, candle, pipeline) == []

    pipeline.changes[(symbol, Timeframe.M5)].append(StructureChange(
        symbol=symbol, timeframe=Timeframe.M5, type="CHOCH", direction=Direction.BULLISH,
        break_level_price=100, timestamp=4,
    ))
    scenarios = manager.generate_top_down(symbol, candle, pipeline)
    assert len(scenarios) == 1
    assert scenarios[0].direction == "LONG"
    assert scenarios[0].stop_loss_price < 97
    assert scenarios[0].take_profit_prices[0] == 120
