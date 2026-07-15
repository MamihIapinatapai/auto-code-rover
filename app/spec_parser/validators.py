"""Calibration and semantic validation for structured specs."""

from __future__ import annotations

import re

from app.spec_parser.grounding import enforceable_co_fix
from app.spec_parser.ac_markers import ac_ids_in_script, parse_ac_sections
from app.spec_parser.calibration_gate import (
    CalibrationVerdict,
    classify_stderr_script_error,
    evaluate_calibration,
    strict_legacy_ok,
)
from app.spec_parser.schema import (
    CriterionResult,
    ExecutionEvidence,
    FailureAnchor,
    SandboxExecutionResult,
    ScriptLintReport,
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
    lint_report: ScriptLintReport | None = None,
    *,
    issue_text: str = "",
) -> tuple[bool, str, list[str], list[str]]:
    """Return passed, feedback, failed_ac_ids, uncovered_co_fix."""
    verdict = evaluate_calibration(
        spec, evidence, script_content, lint_report, issue_text=issue_text
    )
    return (
        verdict.passed,
        verdict.reason,
        verdict.failed_ac_ids,
        verdict.uncovered_co_fix,
    )


def validate_calibration_legacy(
    task_type: TaskType,
    spec: StructuredSpecification,
    result: SandboxExecutionResult,
) -> tuple[bool, str]:
    return strict_legacy_ok(task_type, result, "")


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
    *,
    issue_text: str = "",
) -> ExecutionEvidence:
    stderr = result.stderr
    is_err, err_reason = classify_stderr_script_error(
        spec.task_type, stderr, script_content, issue_text=issue_text
    )
    if is_err:
        label = err_reason.split()[0]
        return ExecutionEvidence(
            calibration_passed=False,
            calibration_error=label,
            overall_exit_code=result.exit_code,
            execution_mode="holistic",
        )

    must_ids = [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]
    section_map = parse_ac_sections(script_content, must_ids)
    ac_ids = sorted(section_map.ac_ids) or must_ids
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

    primary = None
    if ac_ids and buggy_failed:
        primary = ac_ids[0]

    legacy_ok, _ = strict_legacy_ok(
        spec.task_type,
        result,
        script_content,
        issue_text=issue_text,
    )
    uncovered = [
        e
        for e in enforceable_co_fix(spec, issue_text)
        if e.lower() not in script_content.lower()
    ]
    calib_ok = legacy_ok and not uncovered

    return ExecutionEvidence(
        calibration_passed=calib_ok,
        overall_exit_code=result.exit_code,
        per_criterion_results=per_criterion,
        primary_failure_ac_id=primary,
        execution_mode="holistic",
        preflight_passed=True,
    )
