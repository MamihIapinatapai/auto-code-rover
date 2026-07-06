"""Prompt templates for wide acceptance script generation."""

from __future__ import annotations

import json

from app.spec_parser.schema import RepoContext, StructuredSpecification

SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an experienced software engineer writing a standalone Python script to validate a REPAIR CONTRACT in a sandbox.

## Requirements
1. Output exactly ONE Python file in a single ```python ... ``` block.
2. Runnable via: python3 <filename>.py
3. Read-only imports; no repo modification; no network.
4. Include print_stacktrace helper:

def print_stacktrace(e: Exception):
    import traceback
    import sys
    tb = traceback.extract_tb(e.__traceback__)
    print("Traceback (most recent call last):", file=sys.stderr)
    for frame in tb:
        line_number = frame.lineno
        code_context = frame.line.strip() if frame.line else "Unknown"
        print(f'  File "{frame.filename}"', file=sys.stderr)
        print(f"    {line_number}: {code_context}", file=sys.stderr)
    print(f"{e.__class__.__name__}: {e}", file=sys.stderr)

## Wide acceptance rules
1. Structure BY AC: use `# --- AC-XXX: short description ---` per criterion id (exact id from spec).
2. Cover ALL must ACs AND fix_scope.co_fix_required AND prerequisite probes.
3. Respect negative_constraints.
4. No weak checks like "Not supported not in output" alone.
5. Each AC must raise AssertionError on failure; do NOT catch and return False.
6. Optional: print `AC-XXX FAIL` to stderr before raising (helps calibration).
7. Do NOT use numpy or lambdify(..., 'numpy'). Use sympy subs/evalf for numeric checks.
8. Do NOT use from __future__ imports. Do NOT import get_sympy or path_hack.
9. If fix_scope.prerequisite mentions Relational, include AC-REL testing Ne/Eq output.

BUG_FIX: unpatched codebase must fail; fixed codebase exit 0.
Filename: reproduce_issue.py (BUG_FIX) or test_feature.py (FEATURE).
"""

SCRIPT_USER_TEMPLATE = """## Structured Specification
{structured_spec_json}

## Fix Scope
{fix_scope_json}

## Negative Constraints
{negative_constraints_json}

## co_fix_required
{co_fix_required_list}

## Repository Context
- Repository: {repo_name}
- Test framework: {test_framework}
- Top-level packages: {top_level_packages}

## Sample test excerpt
```
{sample_test_excerpt}
```

Write {script_filename} with AC-separated sections.
Task type: {task_type}
{feedback_section}
"""

FEEDBACK_TEMPLATE = """
## Previous Calibration Failure (round {round_no})
- exit_code: {exit_code}
- validation_reason: {validation_reason}
- failed AC ids: {failed_criteria_ids}
- uncovered co_fix: {uncovered_co_fix}
stderr:
```
{stderr_truncated}
```
"""


def format_script_user(
    spec: StructuredSpecification,
    repo_ctx: RepoContext,
    script_filename: str,
    feedback: str | None,
    round_no: int,
) -> str:
    feedback_section = feedback or ""
    return SCRIPT_USER_TEMPLATE.format(
        structured_spec_json=spec.model_dump_json(indent=2),
        fix_scope_json=json.dumps(spec.fix_scope.model_dump(), indent=2),
        negative_constraints_json=json.dumps(
            [nc.model_dump() for nc in spec.negative_constraints], indent=2
        ),
        co_fix_required_list=", ".join(spec.fix_scope.co_fix_required) or "(none)",
        repo_name=repo_ctx.repo_name,
        test_framework=repo_ctx.test_framework,
        top_level_packages=", ".join(repo_ctx.top_level_packages),
        sample_test_excerpt=repo_ctx.sample_test_excerpt or "(none)",
        script_filename=script_filename,
        task_type=spec.task_type.value,
        feedback_section=feedback_section,
    )


def format_feedback(
    *,
    round_no: int,
    exit_code: int | None,
    validation_reason: str,
    failed_criteria_ids: list[str],
    uncovered_co_fix: list[str],
    stderr_truncated: str,
) -> str:
    return FEEDBACK_TEMPLATE.format(
        round_no=round_no,
        exit_code=exit_code,
        validation_reason=validation_reason,
        failed_criteria_ids=", ".join(failed_criteria_ids) or "(none)",
        uncovered_co_fix=", ".join(uncovered_co_fix) or "(none)",
        stderr_truncated=stderr_truncated[:2000],
    )
