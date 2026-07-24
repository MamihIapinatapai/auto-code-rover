"""BehaviorContract LLM semantic review (v3.4 §3.5.8)."""

from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from app import config
from app.data_structures import MessageThread
from app.model import common as model_common
from app.spec_parser.contract_review_prompts import (
    CONTRACT_REVIEW_SEMANTICS_SYSTEM,
    FINDING_ISSUE_TYPES,
    MIN_EVIDENCE_STEPS,
    VERDICTS,
    format_contract_review_user,
)
from app.spec_parser.recipe_loader import (
    format_recipe_hints_for_prompt,
    match_recipe_hints,
)

_BLOCKING_VERDICTS = frozenset(
    {"revise_expect", "reject_false_fail", "reject_off_must"}
)


def high_risk_reasons(
    contract: dict[str, Any],
    *,
    issue_text: str = "",
    task_id: str = "",
) -> list[str]:
    reasons: list[str] = []
    items = contract.get("items") or []
    for it in items:
        layer = str(it.get("layer") or "")
        if layer in {"web", "async"}:
            reasons.append(f"layer={layer}")
        if it.get("recipe_id"):
            reasons.append(f"recipe_id={it.get('recipe_id')}")
        if str(it.get("expect_confidence") or "") == "low":
            reasons.append("expect_confidence=low")
        if str(it.get("oracle_kind") or "") == "raises" and str(
            it.get("expect_confidence") or ""
        ) == "low":
            reasons.append("raises_probe")
    if contract.get("degraded"):
        reasons.append("degraded=true")
    # Any multi-item S1 contract is high-risk for off_must / weak coverage
    if len(items) >= 3:
        reasons.append("multi_item_s1")
    # Issue Must count heuristic vs single S1 row
    must_hits = len(re.findall(r"(?i)\bmust\b|AC-\d+|requirement", issue_text or ""))
    if must_hits >= 3 and len(items) <= 1:
        reasons.append("narrow_s1_vs_many_musts")
    allow = getattr(config, "spec_parser_contract_llm_review_task_allowlist", None) or []
    if task_id and task_id in allow:
        reasons.append(f"allowlist:{task_id}")
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def should_run_table_llm_review(
    contract: dict[str, Any],
    *,
    issue_text: str = "",
    task_id: str = "",
) -> tuple[bool, list[str]]:
    if not getattr(config, "spec_parser_enable_contract_llm_review", False):
        return False, []
    mode = str(
        getattr(config, "spec_parser_contract_llm_review_mode", "high_risk_only") or "off"
    ).lower()
    if mode in {"off", "false", "0", "no"}:
        return False, []
    reasons = high_risk_reasons(contract, issue_text=issue_text, task_id=task_id)
    if mode == "always":
        return True, reasons or ["mode=always"]
    if mode == "high_risk_only":
        return (bool(reasons), reasons)
    return False, []


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _span_in_corpus(span: str, corpus: str) -> bool:
    if not span:
        return False
    if span in corpus:
        return True
    return _norm_ws(span) in _norm_ws(corpus)


def sanitize_review_result(
    raw: dict[str, Any],
    *,
    issue_text: str,
    contract: dict[str, Any],
    recipe_hints: str = "",
    anchor_summary: str = "",
) -> dict[str, Any]:
    """Sanitize LLM review JSON; illegal verdicts cannot be pass."""
    corpus = "\n".join(
        [
            issue_text or "",
            json.dumps(contract, ensure_ascii=False),
            recipe_hints or "",
            anchor_summary or "",
        ]
    )
    verdict = str(raw.get("verdict") or "").strip()
    if verdict not in VERDICTS:
        verdict = "warning"
        raw = {
            **raw,
            "verdict": verdict,
            "blocking": False,
            "summary": (raw.get("summary") or "") + " [sanitized: illegal verdict]",
        }

    findings_in = raw.get("item_findings") or []
    findings_out: list[dict[str, Any]] = []
    if not isinstance(findings_in, list):
        findings_in = []

    for i, f in enumerate(findings_in):
        if not isinstance(f, dict):
            continue
        issue = str(f.get("issue") or "insufficient_evidence")
        if issue not in FINDING_ISSUE_TYPES:
            issue = "insufficient_evidence"
        chain = f.get("evidence_chain") or []
        if not isinstance(chain, list):
            chain = []
        clean_chain: list[dict[str, Any]] = []
        for step in chain:
            if not isinstance(step, dict):
                continue
            span = str(step.get("span_text") or "")[:120]
            st = str(step.get("source_type") or "derived")
            if st == "derived" and not clean_chain:
                continue
            if st != "derived" and span and not _span_in_corpus(span, corpus):
                continue
            clean_chain.append(
                {
                    "step_id": step.get("step_id") or f"E{len(clean_chain)+1}",
                    "claim": str(step.get("claim") or "")[:200],
                    "source_type": st
                    if st
                    in {
                        "issue_span",
                        "contract_field",
                        "recipe_hint",
                        "anchor_entry",
                        "derived",
                    }
                    else "derived",
                    "source_ref": str(step.get("source_ref") or "")[:120],
                    "span_text": span,
                    "support": step.get("support") or "supports",
                }
            )
        min_steps = MIN_EVIDENCE_STEPS.get(issue, 1)
        if issue != "ok" and len(clean_chain) < min_steps:
            issue = "insufficient_evidence"
            if not clean_chain:
                clean_chain = [
                    {
                        "step_id": "E1",
                        "claim": "insufficient verifiable spans after sanitize",
                        "source_type": "derived",
                        "source_ref": "sanitize",
                        "span_text": "",
                        "support": "neutral",
                    }
                ]
            # insufficient cannot keep reject severity
            sev = "warning"
        else:
            sev = str(f.get("severity") or "info")
            if issue in {"false_fail", "off_must", "weak_degraded", "recipe_misaligned"}:
                if sev not in {"blocking", "warning", "info"}:
                    sev = "blocking"
            elif issue == "insufficient_evidence":
                sev = "warning"

        findings_out.append(
            {
                "finding_id": f.get("finding_id") or f"F{i+1}",
                "must_id": f.get("must_id") or "",
                "issue": issue,
                "severity": sev,
                "claim": str(f.get("claim") or "")[:200],
                "evidence_chain": clean_chain,
                "fix": str(f.get("fix") or "")[:200],
                "confidence": f.get("confidence") or "low",
            }
        )

    # Recompute verdict from findings (do not trust model alone for rejects without evidence)
    blocking = False
    computed = "pass"
    for f in findings_out:
        iss = f.get("issue")
        sev = f.get("severity")
        if iss == "false_fail" and sev == "blocking":
            computed = "reject_false_fail"
            blocking = True
            break
        if iss in {"off_must", "recipe_misaligned"} and sev == "blocking":
            computed = "reject_off_must"
            blocking = True
        elif (
            iss in {"weak_degraded", "quote_drift"}
            and sev == "blocking"
            and computed not in _BLOCKING_VERDICTS
        ):
            computed = "revise_expect"
            blocking = True
        elif iss in {"insufficient_evidence", "weak_degraded", "quote_drift"} and not blocking:
            if computed == "pass":
                computed = "warning"

    # Prefer evidence-backed computed verdict over raw model reject/pass
    if computed in _BLOCKING_VERDICTS:
        verdict = computed
        blocking = True
    elif verdict in _BLOCKING_VERDICTS and computed not in _BLOCKING_VERDICTS:
        # model reject without surviving evidence → downgrade
        verdict = computed if computed != "pass" else "warning"
        blocking = False
    elif verdict == "pass" and computed != "pass":
        verdict = computed
        blocking = computed in _BLOCKING_VERDICTS
    elif verdict == "warning":
        blocking = False
        if computed in _BLOCKING_VERDICTS:
            verdict = computed
            blocking = True
    else:
        if computed != "pass":
            verdict = computed
        blocking = verdict in _BLOCKING_VERDICTS

    return {
        "verdict": verdict,
        "blocking": blocking,
        "item_findings": findings_out,
        "must_coverage_notes": raw.get("must_coverage_notes") or [],
        "self_checks": raw.get("self_checks") or {},
        "summary": str(raw.get("summary") or "")[:200],
        "triggered": True,
    }


def review_to_feedback(review: dict[str, Any]) -> dict[str, Any]:
    """Map semantic review into table_gen_feedback for repair."""
    items = []
    for f in review.get("item_findings") or []:
        if f.get("issue") == "ok":
            continue
        if f.get("severity") not in {"blocking", "warning"}:
            continue
        err = f.get("issue") or "insufficient_evidence"
        if err == "false_fail":
            err = "false_fail"
        elif err in {"weak_degraded", "quote_drift"}:
            err = "weak_degraded"
        elif err in {"off_must", "recipe_misaligned"}:
            err = "off_must"
        else:
            err = "weak_degraded"
        items.append(
            {
                "must_id": f.get("must_id") or "",
                "error_type": err,
                "severity": "blocking"
                if review.get("verdict") in _BLOCKING_VERDICTS
                else "warning",
                "what_is_wrong": f.get("claim") or f.get("fix") or err,
                "allowed_edits": ["expect", "fail_mode", "expect_confidence"],
                "forbidden_edits": ["call_graph", "recipe_id", "layer", "entrypoint"],
            }
        )
    return {
        "blocking": bool(review.get("blocking")),
        "summary_for_filler": review.get("summary") or "semantic review requested repair",
        "items": items,
        "source": "table_llm_review",
    }


def review_contract_semantics(
    *,
    contract: dict[str, Any],
    issue_text: str,
    anchor_summary: str = "",
    task_id: str = "",
    use_llm: bool = True,
) -> dict[str, Any]:
    """Run optional LLM semantic review. Caller must ensure BC already passed."""
    should, reasons = should_run_table_llm_review(
        contract, issue_text=issue_text, task_id=task_id
    )
    if not should:
        return {
            "verdict": "skipped",
            "blocking": False,
            "triggered": False,
            "trigger_reasons": reasons,
            "summary": "table LLM review skipped",
            "item_findings": [],
        }

    cards = match_recipe_hints(issue_text, anchor_summary)
    hints = format_recipe_hints_for_prompt(cards)
    thread = MessageThread()
    thread.add_system(CONTRACT_REVIEW_SEMANTICS_SYSTEM)
    thread.add_user(
        format_contract_review_user(
            issue_text=issue_text,
            contract_json=contract,
            recipe_hints=hints,
            anchor_summary=anchor_summary,
            trigger_reasons=reasons,
        )
    )
    if not use_llm:
        return {
            "verdict": "pass",
            "blocking": False,
            "triggered": True,
            "trigger_reasons": reasons,
            "summary": "offline stub pass",
            "item_findings": [],
        }

    try:
        response, *_ = model_common.SELECTED_MODEL.call(
            thread.to_msg(), response_format="json_object"
        )
        thread.add_model(response)
        raw = json.loads(response) if response.strip().startswith("{") else None
        if raw is None:
            m = re.search(r"\{[\s\S]*\}", response)
            raw = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("contract LLM review failed: {}", e)
        return {
            "verdict": "warning",
            "blocking": False,
            "triggered": True,
            "trigger_reasons": reasons,
            "summary": f"review call failed: {e}",
            "item_findings": [],
            "error": str(e),
        }

    sanitized = sanitize_review_result(
        raw if isinstance(raw, dict) else {},
        issue_text=issue_text,
        contract=contract,
        recipe_hints=hints,
        anchor_summary=anchor_summary,
    )
    sanitized["trigger_reasons"] = reasons
    return sanitized
