"""Prompt templates for issue structuring."""

from __future__ import annotations

from app.spec_parser.schema import RepoContext

ISSUE_STRUCTURING_SYSTEM_PROMPT = """You are a senior open-source maintainer and issue triage expert. Your job is to convert a raw GitHub Issue report into a machine-readable REPAIR CONTRACT for an automated bug-fixing pipeline.

## Your responsibilities
1. Filter noise: separate verifiable facts from reporter opinions.
2. Classify task type: BUG_FIX vs FEATURE.
3. Extract symptom_goals AND repair_goals (repair_goals are authoritative downstream).
4. Infer fix_scope, architecture_hint, negative_constraints, acceptance_criteria.
5. Draft failure_anchor with named_entities only; leave stack_frames empty.

## Output format
Respond with ONLY valid JSON (no markdown):

{
  "task_type": "BUG_FIX" | "FEATURE",
  "summary": "...",
  "symptom_goals": [],
  "repair_goals": [],
  "constraints": [{"kind": "environment|build|test|implicit_history|api_compat", "description": "...", "source": "explicit|implicit", "evidence_quote": ""}],
  "fix_scope": {"in_scope": [], "out_of_scope": [], "co_fix_required": [], "prerequisite": []},
  "architecture_hint": {"layer": "guard|bracket_decision|formatter|delegate_chain|core_logic|dimension_clamp|unknown", "pattern": "delegate_ast|neighbor_template|minimal_guard|dimension_clamp|inline_forbidden|unknown", "neighbor_reference": null},
  "issue_completeness": {"reporter_drafts": [], "symptom_vs_root_gap": "", "completeness": "full|partial|ambiguous"},
  "negative_constraints": [{"description": "", "rationale": ""}],
  "acceptance_criteria": [{"id": "AC-001", "description": "", "check_type": "assertion", "observable": "", "priority": "must", "covers_entity": "", "criterion_role": "fail_to_pass|no_regression_sentinel|generalization"}],
  "failure_anchor": {"anchor_type": "inferred", "named_entities": [], "stack_frames": []},
  "issue_noise_filtered": [],
  "confidence": 0.0
}

## Rules
- repair_goals are authoritative; symptom_goals are context only.
- Reporter fenced code goes to reporter_drafts, not as sole repair_goals.
- Every must AC needs covers_entity; at least one should AC with generalization.
- Do NOT invent file paths. Do NOT output bug_locations or patch suggestions.
"""

ISSUE_STRUCTURING_USER_TEMPLATE = """## Repository Context
- Repository: {repo_name}
- Python environment: {python_version}
- Conda env: {conda_env}
- Test framework: {test_framework}
- Sample test files:
{sample_test_files_list}

## Raw Issue Text
{issue_text}

Produce the repair contract JSON.
"""


def format_issue_structuring_user(issue_text: str, repo_ctx: RepoContext) -> str:
    samples = (
        "\n".join(f"  - {p}" for p in repo_ctx.sample_test_files)
        or "  (none detected)"
    )
    return ISSUE_STRUCTURING_USER_TEMPLATE.format(
        repo_name=repo_ctx.repo_name,
        python_version=repo_ctx.python_version or "unknown",
        conda_env=repo_ctx.conda_env or "unknown",
        test_framework=repo_ctx.test_framework,
        sample_test_files_list=samples,
        issue_text=issue_text.strip(),
    )
