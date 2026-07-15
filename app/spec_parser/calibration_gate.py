"""Single calibration gate for static + dynamic acceptance validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app import config
from app.spec_parser.ac_markers import parse_ac_sections
from app.spec_parser.grounding import enforceable_co_fix
from app.spec_parser.schema import (
    ExecutionEvidence,
    SandboxExecutionResult,
    ScriptLintReport,
    StructuredSpecification,
    TaskType,
)

_AC_FAIL_RE = re.compile(r"AC-[A-Z0-9]+\s+FAIL", re.IGNORECASE)
_IMPORT_ERR_RE = re.compile(
    r"(ImportError|ModuleNotFoundError|No module named)",
    re.IGNORECASE,
)
_NO_MODULE_RE = re.compile(
    r"No module named ['\"]?([A-Za-z0-9_.]+)",
    re.IGNORECASE,
)
# Unrelated deps that often cause false F2P calibration when missing.
_ENV_BLACKLIST_MODULES = frozenset(
    {
        "pytest",
        "sympy",
        "numpy",
        "pandas",
        "torch",
        "tensorflow",
        "sklearn",
        "scipy",
    }
)
_SYMPTOM_EXCEPTIONS = (
    "ValueError",
    "TypeError",
    "KeyError",
    "AttributeError",
    "RuntimeError",
    "IndexError",
    "ZeroDivisionError",
)


@dataclass
class CalibrationVerdict:
    passed: bool
    reason: str
    failed_ac_ids: list[str]
    uncovered_co_fix: list[str]
    stage: Literal["preflight", "sandbox", "gate"] = "gate"


def _issue_about_imports(issue_text: str) -> bool:
    blob = issue_text.lower()
    return any(
        k in blob
        for k in (
            "importerror",
            "import error",
            "module not found",
            "no module named",
            "cannot import",
        )
    )


def _feature_not_implemented_fail_ok(stderr: str, script_content: str) -> bool:
    blob = stderr + script_content
    return "NOT_IMPLEMENTED" in blob and "AssertionError" in stderr


def _missing_module_name(stderr: str) -> str | None:
    m = _NO_MODULE_RE.search(stderr)
    if not m:
        return None
    return m.group(1).split(".", 1)[0].lower()


def _is_blacklisted_env_import(stderr: str, issue_text: str) -> bool:
    """True when missing module is a known env noise dep not mentioned in Issue."""
    mod = _missing_module_name(stderr)
    if not mod or mod not in _ENV_BLACKLIST_MODULES:
        return False
    blob = (issue_text or "").lower()
    if mod in blob:
        return False
    return True


def _has_intentional_ac_failure(stderr: str, script_content: str = "") -> bool:
    blob = stderr + "\n" + script_content
    if _AC_FAIL_RE.search(stderr):
        return True
    if "AssertionError" in stderr and "NOT_IMPLEMENTED" in blob:
        return True
    return False


def classify_stderr_script_error(
    task_type: TaskType,
    stderr: str,
    script_content: str,
    *,
    issue_text: str = "",
) -> tuple[bool, str]:
    """Return (is_blocking_error, reason). SyntaxError always blocks."""
    if "SyntaxError" in stderr:
        return True, "SyntaxError in script"

    if not _IMPORT_ERR_RE.search(stderr):
        return False, ""

    # Blacklisted env deps (pytest/sympy/...) are never intentional AC fails.
    if _is_blacklisted_env_import(stderr, issue_text):
        mod = _missing_module_name(stderr) or "unknown"
        return True, f"ENV ModuleNotFoundError for unrelated dependency: {mod}"

    if task_type == TaskType.FEATURE and _feature_not_implemented_fail_ok(
        stderr, script_content
    ):
        return False, ""
    if task_type == TaskType.BUG_FIX and issue_text and _issue_about_imports(issue_text):
        return False, ""
    return True, "ImportError/ModuleNotFoundError in script"


def strict_legacy_ok(
    task_type: TaskType,
    result: SandboxExecutionResult,
    script_content: str,
    *,
    issue_text: str = "",
) -> tuple[bool, str]:
    stderr = result.stderr
    is_err, err_reason = classify_stderr_script_error(
        task_type, stderr, script_content, issue_text=issue_text
    )
    if is_err:
        return False, err_reason

    if task_type == TaskType.BUG_FIX:
        if result.exit_code == 0:
            return False, "BUG_FIX script should fail on buggy codebase"
        if getattr(config, "spec_parser_strict_legacy", True):
            has_assert = "AssertionError" in stderr
            has_ac_fail = _AC_FAIL_RE.search(script_content + stderr)
            has_symptom = any(exc in stderr for exc in _SYMPTOM_EXCEPTIONS)
            if not has_assert and not has_ac_fail and not has_symptom:
                return (
                    False,
                    "Expected AssertionError, AC-XXX FAIL, or symptom exception in stderr",
                )
        else:
            if "AssertionError" not in stderr and "Error" not in stderr:
                return False, "Expected AssertionError or exception in stderr"
        return True, ""

    # FEATURE: must fail, and failure must be intentional AC semantics (v3.1).
    if result.exit_code == 0:
        return False, "FEATURE script should fail when missing"
    if not _has_intentional_ac_failure(stderr, script_content):
        return (
            False,
            "FEATURE requires intentional AC failure "
            "(AC-XXX FAIL or AssertionError NOT_IMPLEMENTED), not ENV/unrelated errors",
        )
    return True, ""


def evaluate_calibration(
    spec: StructuredSpecification,
    evidence: ExecutionEvidence,
    script_content: str,
    lint_report: ScriptLintReport | None = None,
    *,
    issue_text: str = "",
) -> CalibrationVerdict:
    """Single source of truth for calibration_passed."""
    must_ids = [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]
    section_map = parse_ac_sections(script_content, must_ids)

    co_fix_to_enforce = enforceable_co_fix(spec, issue_text)

    if not (script_content or "").strip():
        return CalibrationVerdict(
            passed=False,
            reason="calibration_error: NO_SCRIPT",
            failed_ac_ids=[],
            uncovered_co_fix=list(co_fix_to_enforce),
            stage="preflight",
        )

    if lint_report is not None and not lint_report.passed:
        return CalibrationVerdict(
            passed=False,
            reason=lint_report.blocking_rules[0]
            if lint_report.blocking_rules
            else "preflight failed",
            failed_ac_ids=list(lint_report.missing_ac_ids),
            uncovered_co_fix=list(co_fix_to_enforce),
            stage="preflight",
        )

    if evidence.calibration_error:
        return CalibrationVerdict(
            passed=False,
            reason=f"calibration_error: {evidence.calibration_error}",
            failed_ac_ids=[],
            uncovered_co_fix=list(co_fix_to_enforce),
            stage="sandbox",
        )

    missing = section_map.missing
    uncovered_co_fix = [
        e
        for e in co_fix_to_enforce
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
