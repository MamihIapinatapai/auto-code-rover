"""v3.5 Real Renderer (scheme A) unit tests."""

from __future__ import annotations

import ast

from app.spec_parser.behavior_skeleton import RenderResult, render_s1_script
from app.spec_parser.failure_semantics import check_failure_semantics
from app.spec_parser.recipe_loader import load_recipe_cards


def test_render_blocked_without_fuel():
    contract = {
        "items": [
            {
                "must_id": "M1",
                "layer": "lib",
                "call_graph": ["UnknownApi"],
                "oracle_kind": "equality",
                "expect": {"value": 1},
                "inputs": {},
            }
        ]
    }
    res = render_s1_script(contract, recipe_cards={})
    assert isinstance(res, RenderResult)
    assert res.ok is False
    assert res.script is None
    assert res.reason_code in {
        "NO_USAGE_FUEL",
        "BIND_INPUTS_FAIL",
        "MISSING_SLOT",
        "AMBIGUOUS_API",
    }


def test_render_empty_items_blocked():
    res = render_s1_script({"items": []}, recipe_cards={})
    assert res.ok is False
    assert res.script is None


def test_adaptix_emit_template_real_call():
    cards = load_recipe_cards()
    contract = {
        "items": [
            {
                "must_id": "M1",
                "layer": "lib",
                "recipe_id": "adaptix.name_mapping",
                "call_graph": ["Retort", "name_mapping", "load"],
                "oracle_kind": "equality",
                "expect": {"value": {"x": 1}},
                "inputs": {
                    "name_mapping_args": {"map": {"a": "b"}},
                    "data": {"b": 1},
                    "model": "Model",
                },
            }
        ]
    }
    res = render_s1_script(contract, recipe_cards=cards)
    assert res.ok, (res.reason_code, res.per_must)
    assert res.script is not None
    assert "None  # invoke" not in res.script
    assert "None # invoke" not in res.script
    assert "NOT_IMPLEMENTED" not in res.script
    assert "Retort(recipe=[name_mapping(" in res.script
    tree = ast.parse(res.script)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert calls, "expected product Call AST nodes"
    assert check_failure_semantics(res.script, recipe_id="adaptix.name_mapping", recipe_cards=cards).ok


def test_missing_slot_blocks():
    cards = load_recipe_cards()
    contract = {
        "items": [
            {
                "must_id": "M1",
                "layer": "lib",
                "recipe_id": "adaptix.name_mapping",
                "call_graph": ["Retort", "name_mapping", "load"],
                "oracle_kind": "equality",
                "expect": {"value": 1},
                "inputs": {"data": {}},  # missing name_mapping_args + model
            }
        ]
    }
    res = render_s1_script(contract, recipe_cards=cards)
    assert res.ok is False
    assert res.script is None
    assert res.reason_code == "MISSING_SLOT"
