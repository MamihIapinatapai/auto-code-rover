"""v3.5 failure semantics (EG) unit tests."""

from __future__ import annotations

from app.spec_parser.failure_semantics import (
    check_failure_semantics,
    classify_failure_provenance,
)


def test_eg01_stub_invoke_blocked():
    script = """
def test_ac_M1():
    result = None  # invoke foo
    assert result == 1
"""
    r = check_failure_semantics(script)
    assert "EG-01" in r.blocking


def test_eg01_await_none_blocked():
    script = """
async def test_ac_M1():
    result = await None
    assert result is None
"""
    r = check_failure_semantics(script)
    assert "EG-01" in r.blocking


def test_eg03_raises_self_raise_blocked():
    script = """
import pytest
def test_ac_M1():
    with pytest.raises(ValueError):
        raise ValueError("x")
"""
    r = check_failure_semantics(script)
    assert "EG-03" in r.blocking or "EG-02" in r.blocking


def test_good_product_call_passes():
    script = """
from adaptix import Retort, name_mapping
def test_ac_M1():
    result = Retort(recipe=[name_mapping(name="a")]).load({"a": 1}, dict)
    assert result == {"a": 1}
"""
    r = check_failure_semantics(script)
    assert r.ok, r.blocking


def test_print_only_not_product():
    script = """
def test_ac_M1():
    print("hello")
    assert True
"""
    r = check_failure_semantics(script)
    assert "EG-02" in r.blocking


def test_classify_provenance_missing_defaults():
    out = classify_failure_provenance(script="", evidence=None)
    assert out["failure_provenance"] == "missing"
    assert out["weak_green"] is False
