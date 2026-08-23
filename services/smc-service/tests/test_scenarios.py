import json

import pytest

from src.scenarios import ScenarioTemplate, TemplateStore


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
