"""Tests for calibration gate v3 stderr semantics."""

from app.spec_parser.calibration_gate import (
    classify_stderr_script_error,
    strict_legacy_ok,
)
from app.spec_parser.schema import SandboxExecutionResult, TaskType


def _result(exit_code: int, stderr: str) -> SandboxExecutionResult:
    return SandboxExecutionResult(exit_code=exit_code, stderr=stderr)


def test_feature_allows_import_error_when_not_implemented_wrapped():
    stderr = "AC-HAPPY FAIL\nAssertionError: AC-HAPPY FAIL: NOT_IMPLEMENTED\nImportError: no module"
    script = 'raise AssertionError("AC-HAPPY FAIL: NOT_IMPLEMENTED")'
    is_err, _ = classify_stderr_script_error(
        TaskType.FEATURE, stderr, script
    )
    assert not is_err
    ok, _ = strict_legacy_ok(TaskType.FEATURE, _result(1, stderr), script)
    assert ok


def test_bug_fix_accepts_value_error_in_stderr():
    stderr = "ValueError: invalid cycles"
    script = "# --- AC-001 ---\n..."
    ok, _ = strict_legacy_ok(TaskType.BUG_FIX, _result(1, stderr), script)
    assert ok


def test_bug_fix_rejects_unrelated_importerror():
    stderr = "ImportError: no module named fake_mod"
    ok, reason = strict_legacy_ok(
        TaskType.BUG_FIX, _result(1, stderr), "x", issue_text="ValueError on Permutation"
    )
    assert not ok
    assert "ImportError" in reason


def test_bug_fix_allows_importerror_when_issue_about_imports():
    stderr = "ImportError: no module named foo"
    issue = "ImportError when importing submodule foo"
    is_err, _ = classify_stderr_script_error(
        TaskType.BUG_FIX, stderr, "", issue_text=issue
    )
    assert not is_err
