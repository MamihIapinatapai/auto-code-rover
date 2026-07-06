"""Tests for single calibration gate."""

from app.spec_parser.calibration_gate import evaluate_calibration
from app.spec_parser.schema import (
    AcceptanceCriterion,
    CriterionResult,
    ExecutionEvidence,
    ScriptLintReport,
    StructuredSpecification,
    TaskType,
)


def test_gate_passes_when_evidence_and_markers_align():
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
            )
        ],
    )
    script = "# --- AC-001: test ---\nraise AssertionError('x')"
    evidence = ExecutionEvidence(
        calibration_passed=True,
        per_criterion_results=[
            CriterionResult(
                criterion_id="AC-001",
                passed_on_buggy_code=False,
                expected_failure=True,
            )
        ],
    )
    verdict = evaluate_calibration(spec, evidence, script, None)
    assert verdict.passed


def test_gate_fails_preflight():
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
            )
        ],
    )
    lint = ScriptLintReport(passed=False, blocking_rules=["L1-MISSING-AC"], missing_ac_ids=["AC-001"])
    evidence = ExecutionEvidence(calibration_passed=False)
    verdict = evaluate_calibration(spec, evidence, "pass", lint)
    assert not verdict.passed
    assert verdict.stage == "preflight"
