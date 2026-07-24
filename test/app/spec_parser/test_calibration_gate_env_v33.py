"""Tests for v3.3 Gate ENV vs FEATURE classification."""

from app.spec_parser.calibration_gate import (
    classify_gate_failure_kind,
    classify_stderr_script_error,
    strict_legacy_ok,
)
from app.spec_parser.schema import SandboxExecutionResult, TaskType


def _result(exit_code: int, stderr: str) -> SandboxExecutionResult:
    return SandboxExecutionResult(exit_code=exit_code, stderr=stderr)


def test_yaml_modulenotfound_is_env_even_with_not_implemented():
    stderr = (
        "ModuleNotFoundError: No module named 'yaml'\n"
        "AssertionError: AC-001 FAIL: NOT_IMPLEMENTED"
    )
    script = 'raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")'
    is_err, reason = classify_stderr_script_error(
        TaskType.FEATURE,
        stderr,
        script,
        issue_text="Add structured nosec directives to bandit",
    )
    assert is_err
    assert "yaml" in reason.lower() or "ENV" in reason
    ok, reason2 = strict_legacy_ok(
        TaskType.FEATURE,
        _result(1, stderr),
        script,
        issue_text="Add structured nosec directives to bandit",
    )
    assert not ok
    assert classify_gate_failure_kind(
        TaskType.FEATURE, stderr, script, issue_text="bandit nosec"
    ) == "env"


def test_typing_extensions_is_env():
    stderr = "ModuleNotFoundError: No module named 'typing_extensions'"
    script = "import typing_extensions"
    is_err, reason = classify_stderr_script_error(
        TaskType.FEATURE,
        stderr,
        script,
        issue_text="Flatten dataclass fields in mashumaro",
    )
    assert is_err
    assert "typing_extensions" in reason or "ENV" in reason


def test_product_module_missing_still_allows_not_implemented_wrap():
    """Missing product package with NOT_IMPLEMENTED may still be non-ENV."""
    stderr = (
        "ModuleNotFoundError: No module named 'bandit'\n"
        "AssertionError: AC-001 FAIL: NOT_IMPLEMENTED"
    )
    script = 'raise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")'
    is_err, _ = classify_stderr_script_error(
        TaskType.FEATURE,
        stderr,
        script,
        issue_text="Extend bandit with structured nosec directives",
    )
    # bandit is mentioned in Issue → not transitive ENV blacklist hit
    assert not is_err
