"""Calibration and semantic validation for structured specs."""

from __future__ import annotations

import re

from app.spec_parser.ac_markers import ac_ids_in_script, parse_ac_sections
from app.spec_parser.schema import (
    CriterionResult,
    ExecutionEvidence,
    FailureAnchor,
    SandboxExecutionResult,
    StructuredSpecification,
    TaskType,
)


def validate_structured_spec_semantics(
    spec: StructuredSpecification, issue_text: str
) -> None:
    must_ac = [ac for ac in spec.acceptance_criteria if ac.priority == "must"]
    if not must_ac:
        raise ValueError("At least one must acceptance criterion required")
    if not spec.repair_goals:
        raise ValueError("repair_goals must be non-empty")


def _ac_ids_in_script(script: str) -> set[str]:
    return ac_ids_in_script(script)


def validate_ac_calibration(
    spec: StructuredSpecification,
    evidence: ExecutionEvidence,
    script_content: str,
) -> tuple[bool, str, list[str], list[str]]:
    """Return passed, feedback, failed_ac_ids, uncovered_co_fix."""
    if evidence.calibration_error:
        return (
            False,
            f"calibration_error: {evidence.calibration_error}",
            [],
            list(spec.fix_scope.co_fix_required),
        )

    must_ids = [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]
    script_acs = _ac_ids_in_script(script_content)
    missing_in_script = [aid for aid in must_ids if aid not in script_acs]

    uncovered_co_fix: list[str] = []
    for entity in spec.fix_scope.co_fix_required:
        if entity.lower() not in script_content.lower():
            uncovered_co_fix.append(entity)

    failed_ac: list[str] = []
    for cr in evidence.per_criterion_results:
        if cr.criterion_id in must_ids:
            if cr.expected_failure and cr.passed_on_buggy_code:
                failed_ac.append(cr.criterion_id)

    if missing_in_script:
        return (
            False,
            f"missing AC sections in script: {missing_in_script}",
            missing_in_script,
            uncovered_co_fix,
        )

    if uncovered_co_fix:
        return (
            False,
            f"script does not cover co_fix_required: {uncovered_co_fix}",
            failed_ac,
            uncovered_co_fix,
        )

    if failed_ac:
        return (
            False,
            f"ACs did not fail as expected on buggy code: {failed_ac}",
            failed_ac,
            uncovered_co_fix,
        )

    if (
        evidence.calibration_passed
        and not missing_in_script
        and not uncovered_co_fix
        and not evidence.calibration_error
    ):
        return True, "", [], []

    if not evidence.calibration_passed:
        return False, "calibration_passed is false", failed_ac, uncovered_co_fix

    return True, "", [], []


def validate_calibration_legacy(
    task_type: TaskType,
    spec: StructuredSpecification,
    result: SandboxExecutionResult,
) -> tuple[bool, str]:
    stderr = result.stderr
    if "ImportError" in stderr or "SyntaxError" in stderr:
        return False, "ImportError or SyntaxError in script"
    if task_type == TaskType.BUG_FIX:
        if result.exit_code == 0:
            return False, "BUG_FIX script should fail on buggy codebase"
        if "AssertionError" not in stderr and "Error" not in stderr:
            return False, "Expected AssertionError or exception in stderr"
        return True, ""
    return result.exit_code != 0, "FEATURE script should fail when missing"


def extract_failure_anchor(
    stderr: str, spec: StructuredSpecification
) -> FailureAnchor:
    anchor = spec.failure_anchor or FailureAnchor()
    if "AssertionError" in stderr:
        anchor.anchor_type = "assertion_error"
    for line in stderr.splitlines():
        m = re.search(r'File "([^"]+)".*?(\d+):', line)
        if m:
            anchor.top_frame_file = m.group(1)
            anchor.top_frame_line = int(m.group(2))
            break
    return anchor


def build_execution_result(
    repro_result, trace=None
) -> SandboxExecutionResult:
    return SandboxExecutionResult(
        exit_code=repro_result.returncode,
        stdout=repro_result.stdout or "",
        stderr=repro_result.stderr or "",
        reproduced=repro_result.reproduced,
        trace=trace,
    )


def build_execution_evidence_from_result(
    spec: StructuredSpecification,
    result: SandboxExecutionResult,
    script_content: str,
) -> ExecutionEvidence:
    stderr = result.stderr
    if "ImportError" in stderr:
        return ExecutionEvidence(
            calibration_passed=False,
            calibration_error="ImportError",
            overall_exit_code=result.exit_code,
        )
    if "SyntaxError" in stderr:
        return ExecutionEvidence(
            calibration_passed=False,
            calibration_error="SyntaxError",
            overall_exit_code=result.exit_code,
        )

    ac_ids = sorted(parse_ac_sections(script_content, [
        ac.id for ac in spec.acceptance_criteria if ac.priority == "must"
    ]).ac_ids) or [
        ac.id for ac in spec.acceptance_criteria if ac.priority == "must"
    ]
    per_criterion: list[CriterionResult] = []
    buggy_failed = result.exit_code != 0
    for ac_id in ac_ids:
        per_criterion.append(
            CriterionResult(
                criterion_id=ac_id,
                passed_on_buggy_code=not buggy_failed,
                expected_failure=True,
                message="overall script failed" if buggy_failed else "unexpected pass",
                stderr_excerpt=stderr[:500],
            )
        )

    primary = ac_ids[0] if ac_ids and buggy_failed else None

    legacy_ok, _ = validate_calibration_legacy(
        spec.task_type,
        spec,
        result,
    )
    uncovered = [
        e
        for e in spec.fix_scope.co_fix_required
        if e.lower() not in script_content.lower()
    ]
    calib_ok = legacy_ok and not uncovered

    return ExecutionEvidence(
        calibration_passed=calib_ok,
        overall_exit_code=result.exit_code,
        per_criterion_results=per_criterion,
        primary_failure_ac_id=primary,
    )
