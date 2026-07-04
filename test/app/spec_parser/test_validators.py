"""Tests for AC calibration validators."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    CriterionResult,
    ExecutionEvidence,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.validators import validate_ac_calibration


def test_ac_ids_with_colon_description():
    from app.spec_parser.validators import _ac_ids_in_script

    script = "# --- AC-001: primary failure ---\nraise AssertionError('x')"
    assert _ac_ids_in_script(script) == {"AC-001"}


def test_ac_calibration_passes_when_calibration_passed_flag_set():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="s",
        repair_goals=["fix is_upper and hessenberg"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="o",
            )
        ],
        fix_scope={"co_fix_required": ["_eval_is_upper_hessenberg"]},
    )
    script = """
# --- AC-001 ---
# test _eval_is_upper_hessenberg
raise AssertionError('bug')
"""
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
    ok, _, _, _ = validate_ac_calibration(spec, evidence, script)
    assert ok
