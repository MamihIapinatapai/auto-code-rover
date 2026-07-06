"""Tests for script preflight linter."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import preflight


def test_preflight_missing_ac():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="s",
        repair_goals=["fix"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="o",
            ),
            AcceptanceCriterion(
                id="AC-002",
                description="d2",
                check_type="assertion",
                observable="o2",
            ),
        ],
    )
    script = "# --- AC-001 ---\nraise AssertionError('x')"
    report = preflight(spec, script)
    assert not report.passed
    assert "L1-MISSING-AC" in report.blocking_rules


def test_preflight_weak_sinc_check():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="sinc",
        repair_goals=["fix ccode(sinc(x))"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="ccode(sinc(x))",
                covers_entity="sinc",
            ),
        ],
    )
    script = """
# --- AC-001 ---
from sympy import symbols, sinc, ccode
x = symbols('x')
assert "Not supported" not in ccode(sinc(x))
"""
    report = preflight(spec, script)
    assert "L3-WEAK-ASSERT-SINC" in report.blocking_rules
