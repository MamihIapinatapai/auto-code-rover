"""Unit tests for v3.0 script generation prompts."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    FixScope,
    RepoContext,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_prompts_v3 import (
    BUG_FIX_SCRIPT_SYSTEM_PROMPT,
    FEATURE_SCRIPT_SYSTEM_PROMPT,
    format_feedback_v3,
    format_script_user_v3,
    select_script_system_prompt,
)
from app.spec_parser.script_templates import wrap_generated_body


def _sample_spec(task_type: TaskType = TaskType.BUG_FIX) -> StructuredSpecification:
    return StructuredSpecification(
        task_type=task_type,
        summary="Fix Permutation overlap",
        symptom_goals=["ValueError on overlapping cycles"],
        repair_goals=["Construct identity for non-disjoint cycles"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="overlap identity",
                check_type="assertion",
                observable="Permutation([[0,1],[0,1]]) is identity",
                covers_entity="Permutation",
            ),
            AcceptanceCriterion(
                id="AC-REG",
                description="no regression",
                check_type="no_regression",
                observable="existing Permutation([[0,1],[0,2]]) still works",
                criterion_role="no_regression_sentinel",
            ),
        ],
        fix_scope=FixScope(co_fix_required=["hessenberg"]),
        confidence=0.8,
    )


def _sample_repo_ctx() -> RepoContext:
    return RepoContext(
        repo_name="sympy",
        test_framework="pytest",
        top_level_packages=["sympy"],
        sample_test_excerpt="from sympy import symbols",
    )


def test_select_script_system_prompt_bug_fix():
    assert select_script_system_prompt(TaskType.BUG_FIX) is BUG_FIX_SCRIPT_SYSTEM_PROMPT


def test_select_script_system_prompt_feature():
    assert select_script_system_prompt(TaskType.FEATURE) is FEATURE_SCRIPT_SYSTEM_PROMPT


def test_bug_fix_system_prompt_grounded_co_fix_and_negative_last():
    assert "Grounded co_fix" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "co_fix hints" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "INSUFFICIENT_SPEC" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "place LAST" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "never to skip co_fix" not in BUG_FIX_SCRIPT_SYSTEM_PROMPT


def test_bug_fix_system_prompt_forbids_unrelated_importerror():
    assert "ImportError/SyntaxError are script errors" in BUG_FIX_SCRIPT_SYSTEM_PROMPT


def test_feature_system_prompt_not_implemented_wrapper():
    assert "NOT_IMPLEMENTED" in FEATURE_SCRIPT_SYSTEM_PROMPT
    assert "no_regression_sentinel" in FEATURE_SCRIPT_SYSTEM_PROMPT


def test_format_script_user_v3_includes_import_contract_and_grounding():
    spec = _sample_spec()
    user = format_script_user_v3(
        spec,
        _sample_repo_ctx(),
        issue_text="Calling Permutation([[0,1],[0,1]]) raises ValueError",
        script_filename="reproduce_issue.py",
        feedback=None,
        round_no=1,
    )
    assert "## Import Contract" in user
    assert "## Grounding Policy" in user
    assert "sympy" in user
    assert "ValueError" in user
    assert "Permutation([[0,1],[0,1]])" in user
    assert "## Grounded co_fix" in user
    assert "## co_fix hints" in user
    assert "hessenberg" in user
    assert "Grounded co_fix" in user or "(none)" in user
    assert "covers_entity hint" in user


def test_format_script_user_v3_splits_grounded_and_hints():
    spec = _sample_spec()
    user = format_script_user_v3(
        spec,
        _sample_repo_ctx(),
        issue_text="Calling Permutation([[0,1],[0,1]]) raises ValueError",
        script_filename="reproduce_issue.py",
        feedback=None,
        round_no=1,
    )
    grounded_section = user.split("## Grounded co_fix")[1].split("## co_fix hints")[0]
    hints_section = user.split("## co_fix hints")[1].split("## Regression")[0]
    assert "hessenberg" in hints_section
    assert "hessenberg" not in grounded_section or "(none)" in grounded_section


def test_format_script_user_v3_grounded_co_fix_when_in_issue():
    spec = _sample_spec()
    user = format_script_user_v3(
        spec,
        _sample_repo_ctx(),
        issue_text="hessenberg and Permutation overlap bug",
        script_filename="reproduce_issue.py",
        feedback=None,
        round_no=1,
    )
    grounded_section = user.split("## Grounded co_fix")[1].split("## co_fix hints")[0]
    assert "hessenberg" in grounded_section


def test_format_script_user_v3_regression_ac_ids():
    spec = _sample_spec(TaskType.FEATURE)
    user = format_script_user_v3(
        spec,
        _sample_repo_ctx(),
        issue_text="Add verbose flag",
        script_filename="test_feature.py",
        feedback=None,
        round_no=1,
    )
    assert "AC-REG" in user


def test_format_feedback_v3_includes_task_type_and_stage():
    fb = format_feedback_v3(
        task_type=TaskType.BUG_FIX,
        round_no=2,
        stage="gate",
        validation_reason="missing AC sections",
        failed_criteria_ids=["AC-002"],
        stderr_truncated="AssertionError",
        symptom_alignment_score=0.3,
    )
    assert "task_type: BUG_FIX" in fb
    assert "stage: gate" in fb
    assert "symptom_alignment_score: 0.30" in fb
    assert "NOT_IMPLEMENTED" in fb


def test_wrap_generated_body_includes_scaffold():
    body = "# --- AC-001 ---\nassert True"
    wrapped = wrap_generated_body(body, summary="test summary")
    assert "print_stacktrace" in wrapped
    assert "def main():" in wrapped
    assert 'if __name__ == "__main__":' in wrapped
    assert "# --- AC-001 ---" in wrapped
    assert "assert True" in wrapped


def test_sanitize_generated_body_strips_duplicate_main():
    from app.spec_parser.script_templates import sanitize_generated_body

    body = 'def main():\n    pass\n# --- AC-001 ---\nassert True'
    cleaned = sanitize_generated_body(body)
    assert "def main" not in cleaned
    assert "# --- AC-001 ---" in cleaned


def test_bug_fix_system_prompt_rule_zero_and_symptom_wrap():
    assert "Do NOT define main()" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "ValueError/TypeError" in BUG_FIX_SCRIPT_SYSTEM_PROMPT
    assert "Issue text first" in BUG_FIX_SCRIPT_SYSTEM_PROMPT or "Issue text" in BUG_FIX_SCRIPT_SYSTEM_PROMPT


def test_feature_system_prompt_no_importerror_in_stderr():
    assert "Do NOT let ImportError appear in stderr" in FEATURE_SCRIPT_SYSTEM_PROMPT
