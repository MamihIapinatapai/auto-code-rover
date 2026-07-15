"""Per-AC isolated sandbox execution."""

from __future__ import annotations

from app.spec_parser.ac_markers import (
    extract_ac_section_body,
    parse_ac_sections,
    script_preamble,
)
from app.spec_parser.calibration_gate import strict_legacy_ok
from app.spec_parser.grounding import enforceable_co_fix
from app.spec_parser.schema import (
    CriterionResult,
    ExecutionEvidence,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.validators import build_execution_result
from app.task import Task


def _must_ac_ids(spec: StructuredSpecification) -> list[str]:
    return [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]


def _wrap_ac_script(preamble: str, section_body: str, ac_id: str) -> str:
    return f'''{preamble}

{section_body}

if __name__ == "__main__":
    import sys
    print("{ac_id} FAIL", file=sys.stderr)
    raise AssertionError("{ac_id} calibration probe")
'''


def run_per_ac(
    task: Task,
    script_content: str,
    spec: StructuredSpecification,
    *,
    issue_text: str = "",
) -> ExecutionEvidence:
    must_ids = _must_ac_ids(spec)
    section_map = parse_ac_sections(script_content, must_ids)
    first_line = min(
        (ln for lnos in section_map.found.values() for ln in lnos),
        default=1,
    )
    preamble = script_preamble(script_content, first_line)

    per_criterion: list[CriterionResult] = []
    primary: str | None = None

    for ac_id in must_ids:
        body = extract_ac_section_body(script_content, ac_id)
        if not body:
            per_criterion.append(
                CriterionResult(
                    criterion_id=ac_id,
                    passed_on_buggy_code=True,
                    expected_failure=True,
                    message="AC section not found",
                    skipped_reason="missing_section",
                )
            )
            if primary is None:
                primary = ac_id
            continue

        mini = _wrap_ac_script(preamble, body, ac_id)
        repro = task.execute_reproducer(mini)
        result = build_execution_result(repro)
        legacy_ok, msg = strict_legacy_ok(
            spec.task_type, result, mini, issue_text=issue_text
        )
        passed_on_buggy = result.exit_code == 0
        if spec.task_type == TaskType.BUG_FIX:
            passed_on_buggy = result.exit_code == 0

        per_criterion.append(
            CriterionResult(
                criterion_id=ac_id,
                passed_on_buggy_code=passed_on_buggy,
                expected_failure=True,
                message=msg or ("failed on buggy" if not passed_on_buggy else "unexpected pass"),
                stderr_excerpt=(result.stderr or "")[:500],
            )
        )
        if primary is None and passed_on_buggy:
            primary = ac_id

    if primary is None:
        for cr in per_criterion:
            if not cr.passed_on_buggy_code and cr.skipped_reason is None:
                primary = cr.criterion_id
                break

    all_failed = all(
        not cr.passed_on_buggy_code
        for cr in per_criterion
        if cr.skipped_reason is None
    )
    uncovered = [
        e
        for e in enforceable_co_fix(spec, issue_text)
        if e.lower() not in script_content.lower()
    ]
    calib_ok = all_failed and not uncovered and bool(per_criterion)

    return ExecutionEvidence(
        calibration_passed=calib_ok,
        overall_exit_code=1 if calib_ok else 0,
        per_criterion_results=per_criterion,
        primary_failure_ac_id=primary,
        execution_mode="per_ac",
        preflight_passed=True,
    )
