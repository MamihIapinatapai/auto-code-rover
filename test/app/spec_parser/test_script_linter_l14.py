"""Tests for L14-EMPTY-FAIL (v3.3)."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import count_behavioral_acs, preflight


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


def test_l14_blocks_notimplementederror_only():
    script = """
# --- AC-001 ---
raise NotImplementedError("todo")
"""
    report = preflight(_spec("AC-001"), script)
    assert not report.passed
    assert "L14-EMPTY-FAIL" in report.blocking_rules


def test_l14_blocks_not_implemented_assertion_without_probe():
    script = """
# --- AC-001 ---
raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")
"""
    report = preflight(_spec("AC-001"), script)
    assert "L14-EMPTY-FAIL" in report.blocking_rules


def test_l14_allows_probe_then_not_implemented():
    script = """
# --- AC-001 ---
try:
    from pkg import feature
    assert feature() == 1, "AC-001 FAIL: bad"
except (AttributeError, ImportError):
    raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")
"""
    report = preflight(_spec("AC-001"), script)
    assert "L14-EMPTY-FAIL" not in report.blocking_rules


def test_count_behavioral_acs_empty_fail():
    script = """
# --- AC-001 ---
raise NotImplementedError("x")
# --- AC-002 ---
from pkg import load
assert load(1) == 1, "AC-002 FAIL"
"""
    counts = count_behavioral_acs(script, ["AC-001", "AC-002"])
    assert counts["empty_fail_ac_count"] >= 1
    assert counts["behavioral_ac_count"] >= 1
