"""Single calibration gate for static + dynamic acceptance validation."""

from __future__ import annotations

import json
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
# Transitive / env noise deps (v3.3): missing these must not calib_pass as NOT_IMPLEMENTED.
_ENV_TRANSITIVE_DEFAULT = frozenset(
    {
        "yaml",
        "typing_extensions",
        "packaging",
        "attrs",
        "idna",
        "certifi",
        "urllib3",
        "charset_normalizer",
        "tomli",
        "tomllib",
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

GateFailureKind = Literal["env", "feature", "mixed", "syntax", "none"]
GateTriageClass = Literal[
    "missing_third_party",
    "missing_feature_module",
    "harness_error",
    "feature_fail",
    "pass",
    "unknown",
]


def extract_json_blob(stdout: str) -> str | None:
    """Extract a JSON object/array substring from CLI stdout (bandit harness)."""
    text = stdout or ""
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start < 0:
            continue
        depth = 0
        for i, ch in enumerate(text[start:], start=start):
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except Exception:  # noqa: BLE001
                        break
    return None


def _feature_module_hints() -> frozenset[str]:
    configured = getattr(config, "spec_parser_feature_module_name_hints", None) or []
    return frozenset(str(m).lower() for m in configured)


def classify_gate_triage(
    task_type: TaskType,
    stderr: str,
    script_content: str,
    *,
    issue_text: str = "",
    exit_code: int | None = None,
    stdout: str = "",
) -> GateTriageClass:
    """v3.4 Gate four-way triage (GAT-M1). Fallback maps legacy kinds."""
    if not getattr(config, "spec_parser_enable_gate_triage", True):
        legacy = classify_gate_failure_kind(
            task_type,
            stderr,
            script_content,
            issue_text=issue_text,
            exit_code=exit_code,
        )
        return {
            "env": "missing_third_party",
            "feature": "feature_fail",
            "mixed": "feature_fail",
            "syntax": "harness_error",
            "none": "pass",
        }.get(legacy, "unknown")

    blob = f"{stderr}\n{stdout}"
    if "JSONDecodeError" in blob or (
        "json.loads" in (script_content or "")
        and "JSONDecodeError" in stderr
    ):
        # Prefer harness when parse of stdout failed
        if extract_json_blob(stdout) is None and (
            "json.loads" in script_content or "JSONDecodeError" in stderr
        ):
            return "harness_error"

    if "RuntimeError" in stderr and "no running event loop" in stderr.lower():
        return "harness_error"
    if "run_coroutine_threadsafe" in script_content and "event loop" in stderr.lower():
        return "harness_error"

    if _IMPORT_ERR_RE.search(stderr):
        mod = _missing_module_name(stderr) or ""
        full = ""
        m = _NO_MODULE_RE.search(stderr)
        if m:
            full = m.group(1).lower()
        hints = _feature_module_hints()
        issue_l = (issue_text or "").lower()
        # Feature signal: Issue/hints name the missing module (e.g. sqlfmt.ddl)
        if full and (
            full in hints
            or any(h and h in full for h in hints)
            or (full in issue_l)
            or (mod and mod in issue_l and mod not in _env_transitive_modules())
        ):
            # Prefer feature when not a known transitive env dep
            if mod not in _env_transitive_modules() and mod not in _ENV_BLACKLIST_MODULES:
                return "missing_feature_module"
        if _is_env_import_failure(stderr, issue_text) or mod in _ENV_BLACKLIST_MODULES:
            return "missing_third_party"
        if mod and mod not in _env_transitive_modules():
            # Unknown import: if Issue mentions it → feature module, else third_party-ish
            if _module_mentioned_in_issue(mod, issue_text) or (
                full and full in issue_l
            ):
                return "missing_feature_module"
            return "missing_third_party"
        return "missing_third_party"

    if exit_code == 0 and not stderr.strip():
        return "pass"
    if _has_intentional_ac_failure(stderr, script_content):
        return "feature_fail"
    if "SyntaxError" in stderr:
        return "harness_error"
    if exit_code not in (None, 0):
        return "feature_fail"
    return "unknown"


def feature_signal_ok(triage: GateTriageClass) -> bool:
    """O2: missing_feature_module counted separately from calibration_passed."""
    return triage == "missing_feature_module"


@dataclass
class CalibrationVerdict:
    passed: bool
    reason: str
    failed_ac_ids: list[str]
    uncovered_co_fix: list[str]
    stage: Literal["preflight", "sandbox", "gate"] = "gate"


def _env_transitive_modules() -> frozenset[str]:
    configured = getattr(config, "spec_parser_env_transitive_modules", None)
    if configured:
        return frozenset(str(m).lower() for m in configured)
    return _ENV_TRANSITIVE_DEFAULT


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


def _module_mentioned_in_issue(mod: str, issue_text: str) -> bool:
    blob = (issue_text or "").lower()
    return bool(mod) and mod.lower() in blob


def _is_blacklisted_env_import(stderr: str, issue_text: str) -> bool:
    """True when missing module is a known env noise dep not mentioned in Issue."""
    mod = _missing_module_name(stderr)
    if not mod or mod not in _ENV_BLACKLIST_MODULES:
        return False
    if _module_mentioned_in_issue(mod, issue_text):
        return False
    return True


def _is_transitive_env_import(stderr: str, issue_text: str) -> bool:
    """v3.3: transitive deps (yaml, typing_extensions, …) count as ENV failures."""
    mod = _missing_module_name(stderr)
    if not mod or mod not in _env_transitive_modules():
        return False
    if _module_mentioned_in_issue(mod, issue_text):
        return False
    return True


def _is_env_import_failure(stderr: str, issue_text: str) -> bool:
    return _is_blacklisted_env_import(stderr, issue_text) or _is_transitive_env_import(
        stderr, issue_text
    )


def _has_intentional_ac_failure(stderr: str, script_content: str = "") -> bool:
    blob = stderr + "\n" + script_content
    if _AC_FAIL_RE.search(stderr):
        return True
    if "AssertionError" in stderr and "NOT_IMPLEMENTED" in blob:
        return True
    return False


def classify_gate_failure_kind(
    task_type: TaskType,
    stderr: str,
    script_content: str,
    *,
    issue_text: str = "",
    exit_code: int | None = None,
) -> GateFailureKind:
    """Classify sandbox failure for decision-trace / Gate policy (v3.3)."""
    if "SyntaxError" in stderr:
        return "syntax"
    if not stderr and exit_code == 0:
        return "none"
    if _IMPORT_ERR_RE.search(stderr) and _is_env_import_failure(stderr, issue_text):
        return "env"
    if _IMPORT_ERR_RE.search(stderr) and _feature_not_implemented_fail_ok(
        stderr, script_content
    ):
        # Import noise coexists with intentional AC fail — treat as mixed when ENV-like.
        if _is_env_import_failure(stderr, issue_text):
            return "env"
        return "mixed"
    if task_type == TaskType.FEATURE and _has_intentional_ac_failure(
        stderr, script_content
    ):
        return "feature"
    if _IMPORT_ERR_RE.search(stderr):
        if task_type == TaskType.BUG_FIX and issue_text and _issue_about_imports(
            issue_text
        ):
            return "feature"
        return "env" if _is_env_import_failure(stderr, issue_text) else "mixed"
    return "none"


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

    # ENV deps (pytest/sympy/… and transitive yaml/typing_extensions/…) always block,
    # even when the script wraps the failure as NOT_IMPLEMENTED.
    if _is_env_import_failure(stderr, issue_text):
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

    kind = classify_gate_failure_kind(
        task_type,
        stderr,
        script_content,
        issue_text=issue_text,
        exit_code=result.exit_code,
    )
    if kind == "env":
        mod = _missing_module_name(stderr) or "unknown"
        return False, f"ENV import failure: {mod}"

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
