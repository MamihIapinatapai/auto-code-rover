"""Single calibration gate for static + dynamic acceptance validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app import config
from app.spec_parser.ac_markers import parse_ac_sections
from app.spec_parser.schema import (
    ExecutionEvidence,
    SandboxExecutionResult,
    ScriptLintReport,
    StructuredSpecification,
    TaskType,
)


@dataclass
class CalibrationVerdict:
    passed: bool
    reason: str
    failed_ac_ids: list[str]
    uncovered_co_fix: list[str]
    stage: Literal["preflight", "sandbox", "gate"] = "gate"


def strict_legacy_ok(
    task_type: TaskType,
    result: SandboxExecutionResult,
    script_content: str,
) -> tuple[bool, str]:
    stderr = result.stderr
    if "ImportError" in stderr or "SyntaxError" in stderr:
        return False, "ImportError or SyntaxError in script"
    if task_type == TaskType.BUG_FIX:
        if result.exit_code == 0:
            return False, "BUG_FIX script should fail on buggy codebase"
        if getattr(config, "spec_parser_strict_legacy", True):
            has_assert = "AssertionError" in stderr
            has_ac_fail = re.search(
                r"AC-[A-Z0-9]+\s+FAIL", script_content + stderr, re.IGNORECASE
            )
            if not has_assert and not has_ac_fail:
                return False, "Expected AssertionError or AC-XXX FAIL marker"
        else:
            if "AssertionError" not in stderr and "Error" not in stderr:
                return False, "Expected AssertionError or exception in stderr"
        return True, ""
    return result.exit_code != 0, "FEATURE script should fail when missing"


def evaluate_calibration(
    spec: StructuredSpecification,
    evidence: ExecutionEvidence,
    script_content: str,
    lint_report: ScriptLintReport | None = None,
) -> CalibrationVerdict:
    """Single source of truth for calibration_passed."""
    must_ids = [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]
    section_map = parse_ac_sections(script_content, must_ids)

    if lint_report is not None and not lint_report.passed:
        return CalibrationVerdict(
            passed=False,
            reason=lint_report.blocking_rules[0]
            if lint_report.blocking_rules
            else "preflight failed",
            failed_ac_ids=list(lint_report.missing_ac_ids),
            uncovered_co_fix=list(spec.fix_scope.co_fix_required),
            stage="preflight",
        )

    if evidence.calibration_error:
        return CalibrationVerdict(
            passed=False,
            reason=f"calibration_error: {evidence.calibration_error}",
            failed_ac_ids=[],
            uncovered_co_fix=list(spec.fix_scope.co_fix_required),
            stage="sandbox",
        )

    missing = section_map.missing
    uncovered_co_fix = [
        e
        for e in spec.fix_scope.co_fix_required
        if e.lower() not in script_content.lower()
    ]

    failed_ac: list[str] = []
    for cr in evidence.per_criterion_results:
        if cr.criterion_id in must_ids:
            if cr.expected_failure and cr.passed_on_buggy_code:
                failed_ac.append(cr.criterion_id)

    if missing:
        return CalibrationVerdict(
            passed=False,
            reason=f"missing AC sections in script: {missing}",
            failed_ac_ids=missing,
            uncovered_co_fix=uncovered_co_fix,
            stage="gate",
        )

    if uncovered_co_fix:
        return CalibrationVerdict(
            passed=False,
            reason=f"script does not cover co_fix_required: {uncovered_co_fix}",
            failed_ac_ids=failed_ac,
            uncovered_co_fix=uncovered_co_fix,
            stage="gate",
        )

    if failed_ac:
        return CalibrationVerdict(
            passed=False,
            reason=f"ACs did not fail as expected on buggy code: {failed_ac}",
            failed_ac_ids=failed_ac,
            uncovered_co_fix=uncovered_co_fix,
            stage="gate",
        )

    if not evidence.calibration_passed:
        return CalibrationVerdict(
            passed=False,
            reason="calibration_passed is false",
            failed_ac_ids=failed_ac,
            uncovered_co_fix=uncovered_co_fix,
            stage="sandbox",
        )

    return CalibrationVerdict(
        passed=True,
        reason="",
        failed_ac_ids=[],
        uncovered_co_fix=[],
        stage="gate",
    )


def apply_verdict_to_evidence(
    evidence: ExecutionEvidence, verdict: CalibrationVerdict
) -> ExecutionEvidence:
    return evidence.model_copy(update={"calibration_passed": verdict.passed})
