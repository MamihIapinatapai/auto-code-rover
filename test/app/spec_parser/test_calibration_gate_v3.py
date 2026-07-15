"""Tests for calibration gate v3.1 stderr / intentional-fail semantics."""

from app.spec_parser.calibration_gate import (
    classify_stderr_script_error,
    evaluate_calibration,
    strict_legacy_ok,
)
from app.spec_parser.schema import (
    AcceptanceCriterion,
    ExecutionEvidence,
    SandboxExecutionResult,
    ScriptLintReport,
    StructuredSpecification,
    TaskType,
)


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


def test_feature_rejects_pytest_modulenotfound():
    stderr = "ModuleNotFoundError: No module named 'pytest'"
    script = "import pytest\n# --- AC-001 ---\nassert True"
    is_err, reason = classify_stderr_script_error(
        TaskType.FEATURE, stderr, script, issue_text="Add snapshot support"
    )
    assert is_err
    assert "pytest" in reason or "ENV" in reason
    ok, reason2 = strict_legacy_ok(
        TaskType.FEATURE, _result(1, stderr), script, issue_text="Add snapshot support"
    )
    assert not ok


def test_feature_rejects_exit_nonzero_without_ac_fail():
    stderr = "ValueError: something unrelated"
    script = "# --- AC-001 ---\nraise ValueError('x')"
    ok, reason = strict_legacy_ok(TaskType.FEATURE, _result(1, stderr), script)
    assert not ok
    assert "intentional" in reason.lower() or "AC-" in reason


def test_feature_accepts_ac_fail_assertion():
    stderr = "AssertionError: AC-001 FAIL: NOT_IMPLEMENTED"
    script = '# --- AC-001 ---\nraise AssertionError("AC-001 FAIL: NOT_IMPLEMENTED")'
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
    assert "ImportError" in reason or "ModuleNotFound" in reason


def test_bug_fix_rejects_sympy_env_noise():
    stderr = "ModuleNotFoundError: No module named 'sympy.printing.ccode'"
    is_err, reason = classify_stderr_script_error(
        TaskType.BUG_FIX,
        stderr,
        "import sympy",
        issue_text="Format CREATE TABLE DDL nicely",
    )
    assert is_err
    assert "sympy" in reason.lower() or "ENV" in reason


def test_bug_fix_allows_importerror_when_issue_about_imports():
    stderr = "ImportError: no module named foo"
    issue = "ImportError when importing submodule foo"
    is_err, _ = classify_stderr_script_error(
        TaskType.BUG_FIX, stderr, "", issue_text=issue
    )
    assert not is_err


def test_evaluate_calibration_rejects_empty_script():
    spec = StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="s",
        repair_goals=["g"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="o",
            ),
        ],
    )
    evidence = ExecutionEvidence(calibration_passed=True, overall_exit_code=1)
    verdict = evaluate_calibration(spec, evidence, "", issue_text="feat")
    assert not verdict.passed
    assert "NO_SCRIPT" in verdict.reason


def test_evaluate_calibration_rejects_lint_failure():
    spec = StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="s",
        repair_goals=["g"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="o",
            ),
        ],
    )
    evidence = ExecutionEvidence(calibration_passed=True, overall_exit_code=1)
    lint = ScriptLintReport(passed=False, blocking_rules=["L11-DEAD-AC"])
    verdict = evaluate_calibration(
        spec, evidence, "# --- AC-001 ---\nx=1\n", lint_report=lint
    )
    assert not verdict.passed
    assert verdict.stage == "preflight"
