"""v3.5 failure semantics + renderer unit tests."""

from __future__ import annotations

from app.spec_parser.behavior_skeleton import render_s1_script
from app.spec_parser.failure_semantics import check_failure_semantics
from app.spec_parser.recipe_loader import load_recipe_cards


def test_eg01_stub_invoke_blocked():
    script = '''
def test_ac_M1():
    result = None  # invoke foo
    assert result == 1
'''
    r = check_failure_semantics(script)
    assert "EG-01" in r.blocking


def test_eg03_raises_self_raise_blocked():
    script = '''
import pytest
def test_ac_M1():
    with pytest.raises(ValueError):
        raise ValueError("x")
'''
    r = check_failure_semantics(script)
    assert "EG-03" in r.blocking or "EG-02" in r.blocking


def test_good_product_call_passes():
    script = '''
from adaptix import Retort, name_mapping
def test_ac_M1():
    result = Retort(recipe=[name_mapping(name="a")]).load({"a": 1}, dict)
    assert result == {"a": 1}
'''
    r = check_failure_semantics(script)
    assert r.ok, r.blocking


def test_eg02_allows_main_harness_ac_sections():
    """Free-path scripts use def main() + indented AC bodies — must not EG-02."""
    script = '''
"""doc"""
from aiomonitor import Monitor, start_monitor

def main():
    # --- AC-001: start monitor ---
    with start_monitor(host="127.0.0.1", port=0) as m:
        assert isinstance(m, Monitor)
    # --- AC-002: snapshot API ---
    with start_monitor(host="127.0.0.1", port=0) as m:
        snap = m.take_snapshot()
        assert snap is not None
'''
    r = check_failure_semantics(script)
    assert r.ok, r.blocking


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
    assert "NOT_IMPLEMENTED" not in res.script
    assert "Retort(recipe=[name_mapping(" in res.script
    assert "EG-01" not in check_failure_semantics(res.script).blocking
