"""Tests for Issue-first co_fix / prerequisite grounding (v3.0.2)."""

from unittest.mock import patch

from app.spec_parser.grounding import (
    enforceable_co_fix,
    is_grounded_in_issue,
    split_grounded_scope_items,
)
from app.spec_parser.schema import (
    AcceptanceCriterion,
    FixScope,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import preflight


def _spec(co_fix: list[str] | None = None) -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="s",
        repair_goals=["fix"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="Permutation overlap",
            )
        ],
        fix_scope=FixScope(co_fix_required=co_fix or []),
    )


def test_split_grounded_co_fix_echo_in_issue():
    grounded, hints = split_grounded_scope_items(
        ["hessenberg", "Permutation"],
        "Calling Permutation([[0,1],[0,1]]) raises ValueError",
        _spec().acceptance_criteria,
    )
    assert grounded == ["Permutation"]
    assert hints == ["hessenberg"]


def test_is_grounded_via_ac_observable():
    acs = [
        AcceptanceCriterion(
            id="AC-001",
            description="d",
            check_type="assertion",
            observable="hessenberg form must work",
        )
    ]
    assert is_grounded_in_issue("hessenberg", "short issue", acs)


@patch("app.spec_parser.grounding.config.spec_parser_use_v3_prompts", True)
def test_enforceable_co_fix_v3_only_grounded():
    spec = _spec(co_fix=["hessenberg", "Permutation"])
    assert enforceable_co_fix(
        spec, "Calling Permutation([[0,1],[0,1]]) raises ValueError"
    ) == ["Permutation"]


@patch("app.spec_parser.grounding.config.spec_parser_use_v3_prompts", False)
def test_enforceable_co_fix_v22_all_items():
    spec = _spec(co_fix=["hessenberg", "Permutation"])
    assert enforceable_co_fix(spec, "no overlap") == ["hessenberg", "Permutation"]


@patch("app.spec_parser.grounding.config.spec_parser_use_v3_prompts", True)
def test_preflight_skips_ungrounded_co_fix_when_v3():
    spec = _spec(co_fix=["hessenberg"])
    script = """
# --- AC-001 ---
raise AssertionError('bug')
"""
    report = preflight(
        spec,
        script,
        issue_text="Calling Permutation([[0,1],[0,1]]) raises ValueError",
    )
    assert "L2-COFIX-COVERAGE" not in report.blocking_rules


@patch("app.spec_parser.grounding.config.spec_parser_use_v3_prompts", True)
def test_preflight_requires_grounded_co_fix_when_v3():
    spec = _spec(co_fix=["Permutation"])
    script = """
# --- AC-001 ---
raise AssertionError('bug')
"""
    report = preflight(
        spec,
        script,
        issue_text="Calling Permutation([[0,1],[0,1]]) raises ValueError",
    )
    assert "L2-COFIX-COVERAGE" in report.blocking_rules
