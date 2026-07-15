"""Tests for script linter v3.1 quality rules (L10–L13, hardened L4)."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import preflight


def _spec(*ac_ids: str) -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="feature",
        repair_goals=["add feature"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id=aid,
                description=f"d-{aid}",
                check_type="assertion",
                observable=f"obs-{aid}",
            )
            for aid in ac_ids
        ],
    )


def test_l10_blocks_hasattr_only_ac():
    script = """
# --- AC-001 ---
from pkg import Foo
assert hasattr(Foo(), "bar"), "AC-001 FAIL: missing bar"
"""
    report = preflight(_spec("AC-001"), script)
    assert not report.passed
    assert "L10-EXISTENCE-ONLY" in report.blocking_rules


def test_l10_allows_behavioral_assert_with_hasattr_gate():
    script = """
# --- AC-001 ---
from pkg import load
try:
    obj = load({"x": 1})
except (AttributeError, ImportError):
    raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")
assert obj.value == 1, "AC-001 FAIL: wrong value"
"""
    report = preflight(_spec("AC-001"), script)
    assert "L10-EXISTENCE-ONLY" not in report.blocking_rules


def test_l13_blocks_assert_true():
    script = """
# --- AC-001 ---
x = 1
assert True, "AC-001 FAIL: vacuous"
"""
    report = preflight(_spec("AC-001"), script)
    assert "L13-VACUOUS-ASSERT" in report.blocking_rules


def test_l11_blocks_uncalled_test_functions():
    script = """
# --- AC-001 ---
def test_ac001():
    assert 1 == 1, "AC-001 FAIL"
print("All checks passed")
"""
    report = preflight(_spec("AC-001"), script)
    assert "L11-DEAD-AC" in report.blocking_rules


def test_l11_ok_when_test_called():
    script = """
# --- AC-001 ---
def test_ac001():
    assert 1 == 1, "AC-001 FAIL"
test_ac001()
"""
    report = preflight(_spec("AC-001"), script)
    assert "L11-DEAD-AC" not in report.blocking_rules


def test_l12_blocks_stub_only_ac():
    script = """
# --- AC-001 ---
raise AssertionError("Stub for File exists at results/schema.joblib")
"""
    report = preflight(_spec("AC-001"), script)
    assert "L12-STUB-AC" in report.blocking_rules


def test_l4_blocks_except_pass():
    script = """
# --- AC-001 ---
try:
    from pkg import Client
    Client().post("http://localhost:0/api")
except Exception:
    pass
assert 1 == 1, "AC-001 FAIL: ok"
"""
    report = preflight(_spec("AC-001"), script)
    assert "L4-SWALLOW-EXCEPTION" in report.blocking_rules


def test_l4_allows_except_reraise_assertion():
    script = """
# --- AC-001 ---
try:
    from pkg import feature
    assert feature() == 1, "AC-001 FAIL: bad"
except (AttributeError, ImportError):
    raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")
"""
    report = preflight(_spec("AC-001"), script)
    assert "L4-SWALLOW-EXCEPTION" not in report.blocking_rules
