"""Tests for contract_refiner (M12)."""

from app.spec_parser.contract_refiner import refine
from app.spec_parser.schema import (
    AcceptanceCriterion,
    ArchitectureHint,
    FixScope,
    IssueCompleteness,
    StructuredSpecification,
    TaskType,
)


def test_prerequisite_from_ne_in_reporter_draft():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="ccode sinc",
        repair_goals=["ccode(sinc(x)) should work"],
        architecture_hint=ArchitectureHint(layer="formatter", pattern="delegate_ast"),
        issue_completeness=IssueCompleteness(
            reporter_drafts=["ccode(Piecewise((sin(x)/x, Ne(x, 0)), (1, True)))"]
        ),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="sinc",
                check_type="assertion",
                observable="ccode(sinc(x))",
                priority="must",
                covers_entity="sinc",
                criterion_role="fail_to_pass",
            )
        ],
    )
    out = refine(spec, "ccode(sinc(x)) Ne Piecewise")
    assert "_print_Relational" in out.fix_scope.prerequisite


def test_demote_float_when_not_must_ac():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="mathematica",
        repair_goals=[
            "Implement _print_Derivative",
            "Implement _print_Float for exponents",
        ],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="deriv",
                check_type="assertion",
                observable="Derivative",
                priority="must",
                covers_entity="Derivative",
                criterion_role="fail_to_pass",
            ),
            AcceptanceCriterion(
                id="AC-002",
                description="float",
                check_type="assertion",
                observable="Float",
                priority="should",
                covers_entity="Float",
                criterion_role="fail_to_pass",
            ),
        ],
    )
    out = refine(spec, "Derivative and Float printing")
    assert len(out.repair_goals) == 1
    assert "Float" in out.symptom_goals[0] or any(
        "Float" in g for g in out.symptom_goals
    )
