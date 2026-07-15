"""v3.0 prompt templates: dual System Prompt for BUG_FIX / FEATURE script generation."""

from __future__ import annotations

import json

from app.spec_parser.grounding import split_grounded_scope_items
from app.spec_parser.schema import RepoContext, StructuredSpecification, TaskType

BUG_FIX_SCRIPT_SYSTEM_PROMPT = """You are an expert test engineer practicing reverse test-driven development (reverse-TDD)
for BUG REPRODUCTION.

Write ONLY the acceptance-test body (AC sections). A runtime scaffold (print_stacktrace,
main guard) will be injected automatically — do NOT include them.

Goal: script MUST fail on the current buggy codebase and pass after the correct fix.

Rules:
0. Do NOT define main(), if __name__, or print_stacktrace — the runtime adds them.
1. Output exactly ONE ```python ... ``` block containing AC test logic only.
2. Structure by AC: `# --- AC-XXX: description ---` for each must-level criterion (exact id from spec).
3. Reverse-TDD: derive assertions from Issue text first; use AC.observable only when it quotes Issue.
4. Grounding & scope: hard anchor is Issue text (incl. code blocks). Every assert must trace to Issue
   or to AC.observable that quotes Issue. Do NOT rely on covers_entity alone.
   "Grounded co_fix" in User: each gets `# --- AC-XXX ---` + ≥1 executable assert (comments do not count).
   "co_fix hints" in User: do NOT assert; do not import symbols only mentioned there.
   If a must AC cannot be grounded: AssertionError("AC-XXX FAIL: INSUFFICIENT_SPEC").
   Never invent modules, APIs, or fixtures not evidenced in Issue.
5. Symptom reproduction: failure on buggy code must match the issue symptom (exception type/message/output).
   ImportError/SyntaxError are script errors unless the issue is explicitly about imports.
6. On each AC failure: print `AC-XXX FAIL` to stderr, then raise AssertionError.
   If the issue expects ValueError/TypeError/etc., catch it and re-raise AssertionError
   embedding the original message (do not let raw ImportError reach stderr).
7. Use smallest input from the issue; no large loops or full-repo scans.
8. No network, no file writes, read-only imports.
9. No weak checks (existence-only, "not in output" without behavioral assertion).
10. negative_constraints / no_regression: MUST pass on the current buggy codebase; place LAST.
"""

FEATURE_SCRIPT_SYSTEM_PROMPT = """You are an expert test engineer practicing reverse test-driven development (reverse-TDD)
for FEATURE ACCEPTANCE verification.

Write ONLY the acceptance-test body (AC sections). A runtime scaffold will be injected automatically.

Goal: script MUST fail when the feature is not implemented and pass when correctly implemented.

Rules:
0. Do NOT define main(), if __name__, or print_stacktrace — the runtime adds them.
1. Output exactly ONE ```python ... ``` block containing AC test logic only.
2. Structure by AC: `# --- AC-XXX: description ---` for each must-level criterion (exact id from spec).
3. Reverse-TDD: derive behavioral assertions from Issue text first; use AC.observable only when it quotes Issue.
4. Grounding & scope: hard anchor is Issue text (incl. code blocks). Every assert must trace to Issue
   or to AC.observable that quotes Issue. covers_entity is a hint only.
   "Grounded co_fix" in User: each gets own AC section + ≥1 executable assert.
   "co_fix hints" in User: do NOT assert; do not import symbols only mentioned there.
   Ungrounded must AC → AssertionError("AC-XXX FAIL: INSUFFICIENT_SPEC").
   Never invent modules, APIs, or fixtures not evidenced in Issue.
5. Not-implemented detection: catch AttributeError/ImportError silently, then raise ONLY:
   AssertionError("AC-XXX FAIL: NOT_IMPLEMENTED"). Do NOT let ImportError appear in stderr.
6. no_regression_sentinel ACs (criterion_role): MUST pass on the current codebase — place them LAST;
   use behavioral asserts that verify existing behavior still works.
7. Include happy-path, negative, and edge behavioral asserts (not hasattr-only).
8. Use smallest input from the issue; no large loops or full-repo scans.
9. No network, no file writes, read-only imports.
10. On each AC failure: print `AC-XXX FAIL` to stderr, then raise AssertionError.
"""

SCRIPT_USER_V3_TEMPLATE = """## Task Type
{task_type}

## Import Contract
- Cwd = repo root; import only from: {top_level_packages}
- Copy import style from sample_test_excerpt when present
- Do NOT invent modules, paths, fixtures, or data files

## Grounding Policy (P1 entities are hints only)
- Hard anchor: Issue text (incl. reporter code blocks)
- AC.observable / repair_goals: use only when consistent with Issue; if they contradict Issue, prefer Issue
- Grounded co_fix (below): MUST cover in script; co_fix hints: do NOT assert unless echoed in Issue

## Issue (original — authoritative for symptoms)
{issue_text_excerpt}

## Repair Draft (expected behavior after fix)
{repair_draft_json}

## Observable Acceptance Criteria
{ac_table}

## Fix Scope
{fix_scope_json}

## Negative Constraints
{negative_constraints_json}

## Grounded co_fix (MUST cover — each own AC section with executable assert)
{grounded_co_fix_list}

## co_fix hints (NOT in Issue — do NOT assert; downstream search seeds only)
{co_fix_hints_list}

## Regression AC ids (FEATURE no_regression_sentinel)
{regression_ac_ids}

## Repository Context
repo={repo_name}, framework={test_framework}

## Sample test excerpt (style reference)
```
{sample_test_excerpt}
```

## Task
Write {script_filename} AC test body only. Round {round_no}.
{feedback_section}
"""

FEEDBACK_V3_TEMPLATE = """
## Calibration Failure (round {round_no})
- task_type: {task_type}
- stage: {stage}
- validation_reason: {validation_reason}
- failed AC ids: {failed_criteria_ids}
- symptom_alignment_score: {symptom_alignment_score}
stderr:
```
{stderr_truncated}
```

Fix (BUG_FIX): ensure AC-XXX fails for the issue symptom; wrap ValueError/TypeError into AssertionError with AC-XXX FAIL.
Fix (BUG_FIX): fix unrelated ImportError unless the issue is about imports.
Fix (FEATURE): distinguish NOT_IMPLEMENTED (missing API) from REGRESSION_FAIL (broken existing behavior).
Fix (FEATURE): ImportError must not appear in stderr — only AssertionError with NOT_IMPLEMENTED.
Fix (grounding): do not assert on symbols not in Issue text; prefer Issue over AC.observable when they conflict.
"""


def select_script_system_prompt(task_type: TaskType) -> str:
    if task_type == TaskType.FEATURE:
        return FEATURE_SCRIPT_SYSTEM_PROMPT
    return BUG_FIX_SCRIPT_SYSTEM_PROMPT


def _build_repair_draft_json(spec: StructuredSpecification) -> str:
    payload = {
        "task_type": spec.task_type.value,
        "summary": spec.summary,
        "symptom_summary": "; ".join(spec.symptom_goals) or spec.summary[:300],
        "expected_behavior": list(spec.repair_goals),
        "observable_checks": [ac.model_dump() for ac in spec.acceptance_criteria],
        "fix_scope": spec.fix_scope.model_dump(),
        "architecture_hint": spec.architecture_hint.model_dump(),
        "negative_constraints": [nc.model_dump() for nc in spec.negative_constraints],
        "reporter_hints": list(spec.issue_completeness.reporter_drafts),
        "draft_source": "p1_spec",
        "confidence": spec.confidence,
    }
    return json.dumps(payload, indent=2)


def _format_ac_table(spec: StructuredSpecification) -> str:
    lines: list[str] = []
    for ac in spec.acceptance_criteria:
        lines.append(
            f"- [{ac.id}] {ac.priority} {ac.criterion_role}: {ac.observable}"
            + (f" (covers_entity hint: {ac.covers_entity})" if ac.covers_entity else "")
        )
    return "\n".join(lines) or "(none)"


def _regression_ac_ids(spec: StructuredSpecification) -> str:
    ids = [
        ac.id
        for ac in spec.acceptance_criteria
        if ac.criterion_role == "no_regression_sentinel"
    ]
    return ", ".join(ids) or "(none)"


def format_script_user_v3(
    spec: StructuredSpecification,
    repo_ctx: RepoContext,
    issue_text: str,
    script_filename: str,
    feedback: str | None,
    round_no: int,
    *,
    issue_text_max_chars: int = 8000,
) -> str:
    excerpt = issue_text[:issue_text_max_chars]
    if len(issue_text) > issue_text_max_chars:
        excerpt += "\n... (truncated)"
    grounded_co_fix, co_fix_hints = split_grounded_scope_items(
        spec.fix_scope.co_fix_required,
        issue_text,
        spec.acceptance_criteria,
    )
    return SCRIPT_USER_V3_TEMPLATE.format(
        task_type=spec.task_type.value,
        top_level_packages=", ".join(repo_ctx.top_level_packages) or "(unknown)",
        issue_text_excerpt=excerpt,
        repair_draft_json=_build_repair_draft_json(spec),
        ac_table=_format_ac_table(spec),
        fix_scope_json=json.dumps(spec.fix_scope.model_dump(), indent=2),
        negative_constraints_json=json.dumps(
            [nc.model_dump() for nc in spec.negative_constraints], indent=2
        ),
        grounded_co_fix_list=", ".join(grounded_co_fix) or "(none)",
        co_fix_hints_list=", ".join(co_fix_hints) or "(none)",
        regression_ac_ids=_regression_ac_ids(spec),
        repo_name=repo_ctx.repo_name,
        test_framework=repo_ctx.test_framework,
        sample_test_excerpt=repo_ctx.sample_test_excerpt or "(none)",
        script_filename=script_filename,
        round_no=round_no,
        feedback_section=feedback or "",
    )


def format_feedback_v3(
    *,
    task_type: TaskType,
    round_no: int,
    stage: str,
    validation_reason: str,
    failed_criteria_ids: list[str],
    stderr_truncated: str,
    symptom_alignment_score: float | None = None,
) -> str:
    score_str = (
        f"{symptom_alignment_score:.2f}"
        if symptom_alignment_score is not None
        else "n/a"
    )
    return FEEDBACK_V3_TEMPLATE.format(
        round_no=round_no,
        task_type=task_type.value,
        stage=stage,
        validation_reason=validation_reason,
        failed_criteria_ids=", ".join(failed_criteria_ids) or "(none)",
        symptom_alignment_score=score_str,
        stderr_truncated=stderr_truncated[:2000],
    )
