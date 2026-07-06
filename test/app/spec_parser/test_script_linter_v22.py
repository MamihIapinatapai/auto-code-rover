"""Tests for script_linter L7-L9 (M14)."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import preflight


def _spec() -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="test",
        repair_goals=["fix"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="t",
                check_type="assertion",
                observable="x",
                priority="must",
                covers_entity="x",
                criterion_role="fail_to_pass",
            )
        ],
    )


def test_l7_numpy_lambdify_blocked():
    script = """
# --- AC-001: test ---
def test_ac001():
    from sympy import lambdify, symbols, sinc
    x = symbols('x')
    lambdify(x, sinc(x), 'numpy')
"""
    report = preflight(_spec(), script)
    assert "L7-NUMPY-LAMBDA" in report.blocking_rules


def test_l8_future_import_blocked():
    script = """# --- AC-001: test ---
from sympy import symbols
from __future__ import print_function
x = symbols('x')
"""
    report = preflight(_spec(), script)
    assert "L8-FUTURE-IMPORT" in report.blocking_rules


def test_l9_fake_import_blocked():
    script = "from get_sympy import path_hack\npath_hack()\n"
    report = preflight(_spec(), script)
    assert "L9-FAKE-IMPORT" in report.blocking_rules
