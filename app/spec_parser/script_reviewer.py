"""v3.2/v3.3 LLM reviewer: translate lint/gate + Issue gaps into generator feedback."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app import config
from app.data_structures import MessageThread
from app.model.gpt import common
from app.spec_parser.evidence_chain import (
    coverage_priority_actions,
    migrate_alignment_to_chain,
    parse_coverage_items,
    sanitize_coverage_items,
)
from app.spec_parser.schema import (
    ReviewBlockingFix,
    ReviewDiagnosis,
    ReviewGateFix,
    ReviewIssueGap,
    ScriptLintReport,
    ScriptReviewReport,
    TaskType,
)
from app.spec_parser.script_review_prompts import (
    SCRIPT_REVIEW_SYSTEM_PROMPT,
    format_script_review_user,
)

_SWALLOW_PASS_RE = re.compile(
    r"except\s*(?:\([^)]*\)|[\w.,\s]+)?\s*:\s*pass\b",
    re.IGNORECASE,
)
_STUB_RE = re.compile(r'AssertionError\s*\(\s*[\'"]Stub\b', re.IGNORECASE)
_ASSERT_TRUE_RE = re.compile(r"\bassert\s+True\b")


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _is_illegal_rewrite(text: str) -> bool:
    if not text or not text.strip():
        return False
    if _SWALLOW_PASS_RE.search(text) and "AssertionError" not in text:
        # allow "except SpecificError: pass" only if not bare Exception
        if re.search(r"except\s+Exception\s*:", text) or re.search(
            r"except\s*:", text
        ):
            return True
        if re.search(r"except\s+BaseException\s*:", text):
            return True
    if _STUB_RE.search(text):
        return True
    if _ASSERT_TRUE_RE.search(text) and "assert True" in text.replace(" ", " "):
        # reject suggesting assert True as the fix
        if re.search(r"assert\s+True\b", text) and "FAIL" not in text:
            return True
    return False


def _parse_diagnosis(raw: Any) -> ReviewDiagnosis:
    if isinstance(raw, dict):
        return ReviewDiagnosis.model_validate(raw)
    return ReviewDiagnosis()


def _parse_gate_fixes(raw: Any) -> list[ReviewGateFix]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [
            ReviewGateFix(kind="other", evidence=raw, legal_rewrite="", why="")
        ]
    if not isinstance(raw, list):
        return []
    out: list[ReviewGateFix] = []
    for item in raw:
        if isinstance(item, str):
            out.append(
                ReviewGateFix(kind="other", evidence=item, legal_rewrite="", why="")
            )
        elif isinstance(item, dict):
            out.append(ReviewGateFix.model_validate(item))
    return out


def _parse_ordered_actions(data: dict[str, Any]) -> list[str]:
    actions = data.get("ordered_actions")
    if isinstance(actions, list):
        return [str(x) for x in actions if str(x).strip()]
    if isinstance(actions, str) and actions.strip():
        return [line.strip() for line in actions.splitlines() if line.strip()]
    # Legacy compatibility: pass_to_generator → ordered_actions
    legacy = data.get("pass_to_generator")
    if isinstance(legacy, str) and legacy.strip():
        return [line.strip() for line in legacy.splitlines() if line.strip()]
    return []


def sanitize_review(report: ScriptReviewReport) -> ScriptReviewReport:
    """Drop rewrite suggestions that would re-introduce blocking anti-patterns."""
    kept_fixes: list[ReviewBlockingFix] = []
    deferred = list(report.deferred_issue_gaps)
    changed = False
    for fix in report.blocking_fixes:
        if _is_illegal_rewrite(fix.legal_rewrite):
            changed = True
            deferred.append(
                f"dropped illegal blocking rewrite for {fix.rule}: {fix.bad_pattern[:120]}"
            )
            continue
        kept_fixes.append(fix)
    kept_gates: list[ReviewGateFix] = []
    for gfix in report.gate_fixes:
        if gfix.kind == "env_not_script":
            if gfix.legal_rewrite and gfix.legal_rewrite.strip():
                changed = True
                gfix = gfix.model_copy(update={"legal_rewrite": ""})
            kept_gates.append(gfix)
            continue
        if _is_illegal_rewrite(gfix.legal_rewrite):
            changed = True
            deferred.append(
                f"dropped illegal gate rewrite ({gfix.kind}): {gfix.evidence[:120]}"
            )
            continue
        kept_gates.append(gfix)
    kept_gaps: list[ReviewIssueGap] = []
    for gap in report.issue_alignment:
        if _is_illegal_rewrite(gap.legal_rewrite):
            changed = True
            gap = gap.model_copy(
                update={
                    "superseded_by_blocking": True,
                    "legal_rewrite": "",
                    "detail": gap.detail + " [illegal rewrite stripped]",
                }
            )
            deferred.append(gap.detail[:200])
        kept_gaps.append(gap)

    chain = list(report.issue_coverage_chain)
    if not chain and kept_gaps and getattr(
        config, "spec_parser_enable_evidence_chain", True
    ):
        chain = migrate_alignment_to_chain(kept_gaps)
        changed = True
    kept_chain, chain_deferred, chain_changed = sanitize_coverage_items(
        chain, is_illegal_rewrite=_is_illegal_rewrite
    )
    if chain_changed:
        changed = True
        deferred.extend(chain_deferred)

    # Gate env: strip non-empty rewrites if diagnosis says gate_env
    if report.diagnosis.failure_class == "gate_env":
        cleaned_gates: list[ReviewGateFix] = []
        for gfix in kept_gates:
            if gfix.legal_rewrite and gfix.legal_rewrite.strip():
                changed = True
                gfix = gfix.model_copy(update={"legal_rewrite": ""})
            cleaned_gates.append(gfix)
        kept_gates = cleaned_gates

    if (
        not changed
        and kept_fixes == report.blocking_fixes
        and kept_gates == report.gate_fixes
        and kept_chain == report.issue_coverage_chain
    ):
        return report
    return report.model_copy(
        update={
            "blocking_fixes": kept_fixes,
            "gate_fixes": kept_gates,
            "issue_alignment": kept_gaps,
            "issue_coverage_chain": kept_chain,
            "deferred_issue_gaps": deferred,
            "sanitized": True,
        }
    )


def parse_review_response(
    text: str,
    *,
    stage: str,
    round_no: int,
) -> ScriptReviewReport:
    data = _extract_json_object(text)
    if not data:
        return ScriptReviewReport(
            stage=stage,  # type: ignore[arg-type]
            round_no=round_no,
            ordered_actions=[],
            raw_response=text,
            parse_ok=False,
        )
    fixes = []
    for item in data.get("blocking_fixes") or []:
        if isinstance(item, dict):
            fixes.append(ReviewBlockingFix.model_validate(item))
    gaps = []
    for item in data.get("issue_alignment") or []:
        if isinstance(item, dict):
            gaps.append(ReviewIssueGap.model_validate(item))
    deferred = data.get("deferred_issue_gaps") or []
    if isinstance(deferred, str):
        deferred = [deferred]
    decision_summary = data.get("decision_summary") or {}
    if not isinstance(decision_summary, dict):
        decision_summary = {}
    report = ScriptReviewReport(
        stage=stage,  # type: ignore[arg-type]
        round_no=round_no,
        diagnosis=_parse_diagnosis(data.get("diagnosis")),
        blocking_fixes=fixes,
        gate_fixes=_parse_gate_fixes(data.get("gate_fixes")),
        issue_alignment=gaps,
        deferred_issue_gaps=[str(x) for x in deferred],
        ordered_actions=_parse_ordered_actions(data),
        issue_coverage_chain=parse_coverage_items(data.get("issue_coverage_chain")),
        decision_summary=decision_summary,
        raw_response=text,
        parse_ok=True,
    )
    return sanitize_review(report)


def format_review_feedback(
    report: ScriptReviewReport,
    *,
    validation_reason: str = "",
    blocking_rules: list[str] | None = None,
) -> str:
    """Format reviewer output for ScriptGenerator feedback_section."""
    rules = blocking_rules or [f.rule for f in report.blocking_fixes]
    lines = [
        "## Script Reviewer Feedback (advisory; lint/Gate win on conflict)",
        "If reviewer conflicts with lint, follow lint.",
        f"- stage: {report.stage}",
        f"- round: {report.round_no}",
        f"- machine validation_reason: {validation_reason}",
        f"- blocking_rules: {rules}",
        f"- diagnosis.failure_class: {report.diagnosis.failure_class}",
        f"- diagnosis.summary: {report.diagnosis.summary}",
        "",
        "### Absolute constraints",
        "You MUST clear all machine lint blocking rules after this rewrite.",
        "Forbidden: except Exception: pass; Stub-only; existence-only AC; uncalled test_*.",
        "",
        "### blocking_fixes (do these first)",
    ]
    if report.blocking_fixes:
        for i, fix in enumerate(report.blocking_fixes, 1):
            lines.append(f"{i}. [{fix.rule}] bad: {fix.bad_pattern}")
            lines.append(f"   legal_rewrite: {fix.legal_rewrite}")
            lines.append(f"   why_legal: {fix.why_legal}")
    else:
        lines.append("(none parsed — still clear machine blocking_rules)")

    if report.gate_fixes:
        lines.append("")
        lines.append("### gate_fixes")
        for g in report.gate_fixes:
            lines.append(f"- ({g.kind}) evidence: {g.evidence}")
            if g.legal_rewrite:
                lines.append(f"  legal_rewrite: {g.legal_rewrite}")
            if g.why:
                lines.append(f"  why: {g.why}")

    if report.issue_coverage_chain and getattr(
        config, "spec_parser_enable_evidence_chain", True
    ):
        lines.append("")
        lines.append(
            "### issue_coverage_chain (Issue Must audit — do not invent symbols)"
        )
        for it in report.issue_coverage_chain:
            lines.append(
                f"- [{it.verdict}] {it.issue_item_id or '?'} "
                f"expected={it.expected_layer} actual={it.actual_layer} "
                f"strength={it.assertion_strength} ac={it.ac_id}"
            )
            if it.issue_quote:
                lines.append(f"  quote: {it.issue_quote[:160]}")
            if it.legal_rewrite:
                lines.append(f"  legal_rewrite: {it.legal_rewrite}")
        priority = coverage_priority_actions(report.issue_coverage_chain)
        if priority:
            lines.append("")
            lines.append(
                "### coverage_priority (after clearing blocking lint/gate)"
            )
            lines.append("1. Fix all missing Must items")
            lines.append("2. Fix wrong_layer before weak_assert")
            for p in priority:
                lines.append(f"- {p}")

    if report.decision_summary:
        lines.append("")
        lines.append("### decision_summary")
        lines.append(json.dumps(report.decision_summary, ensure_ascii=False))

    active_gaps = [g for g in report.issue_alignment if not g.superseded_by_blocking]
    if active_gaps:
        lines.append("")
        lines.append("### issue_alignment (Issue-only; do not invent APIs)")
        for g in active_gaps:
            lines.append(f"- ({g.kind}) {g.detail}")
            if g.legal_rewrite:
                lines.append(f"  rewrite: {g.legal_rewrite}")

    if report.deferred_issue_gaps:
        lines.append("")
        lines.append("### deferred_issue_gaps")
        for d in report.deferred_issue_gaps:
            lines.append(f"- {d}")

    lines.append("")
    lines.append("### ordered_actions")
    if report.ordered_actions:
        for action in report.ordered_actions:
            lines.append(f"- {action}")
    else:
        lines.append("(empty — use blocking_fixes / gate_fixes above)")
    return "\n".join(lines)


class ScriptReviewer:
    def review(
        self,
        *,
        issue_text: str,
        script_content: str,
        task_type: TaskType | str,
        stage: str,
        round_no: int,
        lint_report: ScriptLintReport | None = None,
        validation_reason: str = "",
        failed_criteria_ids: list[str] | None = None,
        stderr_excerpt: str = "",
        exit_code: int | None = None,
        use_llm: bool = True,
    ) -> tuple[ScriptReviewReport, MessageThread]:
        thread = MessageThread()
        thread.add_system(SCRIPT_REVIEW_SYSTEM_PROMPT)
        thread.add_user(
            format_script_review_user(
                issue_text=issue_text,
                script_content=script_content,
                task_type=task_type,
                stage=stage,
                round_no=round_no,
                lint_report=lint_report,
                validation_reason=validation_reason,
                failed_criteria_ids=failed_criteria_ids,
                stderr_excerpt=stderr_excerpt,
                exit_code=exit_code,
            )
        )
        if not use_llm:
            report = ScriptReviewReport(
                stage=stage,  # type: ignore[arg-type]
                round_no=round_no,
                ordered_actions=[validation_reason] if validation_reason else [],
                parse_ok=False,
                raw_response="",
            )
            return report, thread

        try:
            response, *_ = common.SELECTED_MODEL.call(
                thread.to_msg(), response_format=None
            )
            thread.add_model(response)
            report = parse_review_response(
                response, stage=stage, round_no=round_no
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Script reviewer LLM failed: {}", exc)
            report = ScriptReviewReport(
                stage=stage,  # type: ignore[arg-type]
                round_no=round_no,
                ordered_actions=[],
                parse_ok=False,
                raw_response=str(exc),
            )
        return report, thread
