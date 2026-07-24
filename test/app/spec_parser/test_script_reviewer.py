"""Tests for v3.2 script reviewer + refined L4."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    ReviewBlockingFix,
    ReviewDiagnosis,
    ReviewGateFix,
    ScriptLintReport,
    ScriptReviewReport,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_linter import preflight
from app.spec_parser.script_review_prompts import (
    LINT_RULE_DIGEST,
    SCRIPT_REVIEW_SYSTEM_PROMPT,
    format_script_review_user,
)
from app.spec_parser.script_reviewer import (
    format_review_feedback,
    parse_review_response,
    sanitize_review,
)


def _spec(*ac_ids: str) -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="feature",
        repair_goals=["add feature"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id=aid,
                description=f"d-{aid}",
                check_type="assertion",
                observable=f"obs-{aid}",
            )
            for aid in ac_ids
        ],
    )


def test_review_system_prompt_priority_and_bans():
    assert "Machine lint" in SCRIPT_REVIEW_SYSTEM_PROMPT or "lint" in SCRIPT_REVIEW_SYSTEM_PROMPT.lower()
    assert "except Exception: pass" in SCRIPT_REVIEW_SYSTEM_PROMPT
    assert "hidden tests" in SCRIPT_REVIEW_SYSTEM_PROMPT.lower() or "solution" in SCRIPT_REVIEW_SYSTEM_PROMPT.lower()
    assert "ordered_actions" in SCRIPT_REVIEW_SYSTEM_PROMPT
    assert "diagnosis" in SCRIPT_REVIEW_SYSTEM_PROMPT
    assert "do_not_suggest" not in SCRIPT_REVIEW_SYSTEM_PROMPT
    assert "pass_to_generator" not in SCRIPT_REVIEW_SYSTEM_PROMPT


def test_lint_digest_has_bad_good_for_weak_rules():
    assert "L10-EXISTENCE-ONLY" in LINT_RULE_DIGEST
    assert "bad: assert hasattr" in LINT_RULE_DIGEST
    assert "L3-WEAK-ASSERT" in LINT_RULE_DIGEST
    assert "L11-DEAD-AC" in LINT_RULE_DIGEST
    assert "L12-STUB-AC" in LINT_RULE_DIGEST


def test_format_review_user_includes_blocking_and_issue():
    lint = ScriptLintReport(passed=False, blocking_rules=["L4-SWALLOW-EXCEPTION"])
    user = format_script_review_user(
        issue_text="Add aliases to name_mapping.",
        script_content="# --- AC-001 ---\nexcept Exception:\n    pass\n",
        task_type=TaskType.FEATURE,
        stage="preflight",
        round_no=1,
        lint_report=lint,
        validation_reason="preflight failed: L4-SWALLOW-EXCEPTION",
    )
    assert "L4-SWALLOW-EXCEPTION" in user
    assert "Add aliases" in user
    assert "AUTHORITATIVE" in user
    assert "stage=preflight" in user
    assert "one entry per rule" in user
    assert "sample_test" not in user.lower() or "NOT" in user  # must not inject excerpt


def test_format_review_user_gate_stage_env_vs_feature():
    user = format_script_review_user(
        issue_text="Add feature X.",
        script_content="# --- AC-001 ---\nassert True\n",
        task_type=TaskType.FEATURE,
        stage="gate",
        round_no=2,
        lint_report=ScriptLintReport(passed=True),
        validation_reason="gate failed: ENV ImportError",
        stderr_excerpt="ModuleNotFoundError: No module named 'pytest'",
    )
    assert "stage=gate" in user
    assert "gate_env" in user
    assert "env_not_script" in user
    assert "gate_feature" in user


def test_format_review_user_truncation_flags():
    issue = "A" * 7000
    script = "B" * 13000
    user = format_script_review_user(
        issue_text=issue,
        script_content=script,
        task_type=TaskType.FEATURE,
        stage="preflight",
        round_no=1,
        lint_report=None,
    )
    assert '"issue_truncated": true' in user
    assert '"script_truncated": true' in user
    assert "only comment on visible regions" in user
    assert "...(truncated)" in user


def test_parse_and_sanitize_drops_illegal_rewrite():
    raw = """
{
  "diagnosis": {"failure_class": "lint", "summary": "L4 swallow"},
  "blocking_fixes": [
    {
      "rule": "L4-SWALLOW-EXCEPTION",
      "bad_pattern": "except Exception: pass",
      "legal_rewrite": "except Exception:\\n    pass",
      "why_legal": "bad"
    },
    {
      "rule": "L4-SWALLOW-EXCEPTION",
      "bad_pattern": "swallow",
      "legal_rewrite": "except Exception as e:\\n    raise AssertionError(f\\"AC-001 FAIL: {e}\\") from e",
      "why_legal": "re-raises AC FAIL"
    }
  ],
  "gate_fixes": [],
  "issue_alignment": [],
  "deferred_issue_gaps": [],
  "ordered_actions": ["1. Fix L4 by re-raising AssertionError"]
}
"""
    report = parse_review_response(raw, stage="preflight", round_no=2)
    assert report.parse_ok
    assert report.sanitized
    assert len(report.blocking_fixes) == 1
    assert "AssertionError" in report.blocking_fixes[0].legal_rewrite
    assert report.ordered_actions[0].startswith("1. Fix L4")
    assert report.diagnosis.failure_class == "lint"


def test_parse_legacy_pass_to_generator_and_string_gate_fixes():
    raw = """
{
  "blocking_fixes": [],
  "gate_fixes": ["make AC-001 raise NOT_IMPLEMENTED"],
  "issue_alignment": [],
  "deferred_issue_gaps": [],
  "do_not_suggest": ["except: pass"],
  "pass_to_generator": "1. Fix gate\\n2. Then Issue gaps"
}
"""
    report = parse_review_response(raw, stage="gate", round_no=1)
    assert report.parse_ok
    assert len(report.gate_fixes) == 1
    assert report.gate_fixes[0].kind == "other"
    assert "NOT_IMPLEMENTED" in report.gate_fixes[0].evidence
    assert report.ordered_actions == ["1. Fix gate", "2. Then Issue gaps"]


def test_sanitize_clears_env_gate_rewrite():
    report = ScriptReviewReport(
        stage="gate",
        round_no=1,
        gate_fixes=[
            ReviewGateFix(
                kind="env_not_script",
                evidence="ModuleNotFoundError: pytest",
                legal_rewrite="pip install pytest",
                why="env",
            )
        ],
    )
    cleaned = sanitize_review(report)
    assert cleaned.sanitized
    assert cleaned.gate_fixes[0].legal_rewrite == ""


def test_format_review_feedback_lint_wins_prefix():
    report = ScriptReviewReport(
        stage="preflight",
        round_no=1,
        diagnosis=ReviewDiagnosis(failure_class="lint", summary="stub AC"),
        blocking_fixes=[
            ReviewBlockingFix(
                rule="L12-STUB-AC",
                bad_pattern="Stub",
                legal_rewrite="call api(); assert x == 1",
                why_legal="behavioral",
            )
        ],
        ordered_actions=["Replace Stub with behavioral assert"],
    )
    fb = format_review_feedback(
        report,
        validation_reason="preflight failed: L12-STUB-AC",
        blocking_rules=["L12-STUB-AC"],
    )
    assert "follow lint" in fb.lower()
    assert "blocking_fixes" in fb
    assert "L12-STUB-AC" in fb
    assert "ordered_actions" in fb
    assert "Replace Stub" in fb
    assert "diagnosis.failure_class: lint" in fb


def test_l4_allows_specific_exception_pass():
    script = """
# --- AC-001 ---
try:
    load({"a": 1, "b": 2})
    raise AssertionError("AC-001 FAIL: expected ExtraFieldsLoadError")
except ExtraFieldsLoadError:
    pass
"""
    report = preflight(_spec("AC-001"), script)
    assert "L4-SWALLOW-EXCEPTION" not in report.blocking_rules


def test_l4_allows_broad_except_with_assertion_reraise():
    script = """
# --- AC-001 ---
try:
    from pkg import missing_api
    missing_api()
except Exception as e:
    raise AssertionError(f"AC-001 FAIL: NOT_IMPLEMENTED: {e}") from e
"""
    report = preflight(_spec("AC-001"), script)
    assert "L4-SWALLOW-EXCEPTION" not in report.blocking_rules


def test_l4_still_blocks_exception_pass():
    script = """
# --- AC-001 ---
try:
    foo()
except Exception:
    pass
assert 1 == 1, "AC-001 FAIL"
"""
    report = preflight(_spec("AC-001"), script)
    assert "L4-SWALLOW-EXCEPTION" in report.blocking_rules
