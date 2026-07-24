"""Prompts for BehaviorContract repair (table patch) after dual reviews — v2.

Consumes TableGenFeedback (preferred) and can fall back to raw table-review /
script-review excerpts. Separate from initial ``contract_fill_*`` prompts.
"""

from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# TableGenFeedback — canonical fields the repair agent expects
# ---------------------------------------------------------------------------

TABLE_GEN_FEEDBACK_ERROR_TYPES = (
    "false_fail",
    "off_must",
    "weak_degraded",
    "quote_drift",
    "recipe_misaligned",
    "multi_item_inconsistency",
    "script_contract_mismatch",
    "invented_expect",
    "insufficient_evidence",
    "render_error",
)

DEFAULT_ALLOWED_EDITS = ("expect", "fail_mode", "expect_confidence")
DEFAULT_FORBIDDEN_EDITS = ("call_graph", "recipe_id", "layer", "entrypoint")

EMPTY_TABLE_GEN_FEEDBACK: dict[str, Any] = {
    "feedback_id": "TF-empty",
    "source": "merged",
    "blocking": False,
    "summary_for_filler": "no feedback",
    "items": [],
    "filler_instructions": [
        "Only edit allowed fields listed per item",
        "Re-emit full expect envelope for patched must_ids",
        "If insufficient_evidence only: do not invent literals",
    ],
}

CONTRACT_REPAIR_SYSTEM = """
You are the BehaviorContract REPAIR editor for AutoCodeRover Spec Parser v3.4 (v2).

You are NOT the initial table author, NOT a semantic auditor, and NOT a script writer.
Your only job: apply structured reviewer feedback to PATCH contract slots so the
table better matches the Issue. A deterministic Renderer rebuilds pytest later.

==============================================================================
INPUTS YOU WILL RECEIVE
==============================================================================
1) Issue text
2) Current BehaviorContract JSON
3) TableGenFeedback JSON (PREFERRED canonical input) with items[]:
   - must_id, error_type, severity (blocking|warning), what_is_wrong
   - evidence_digest[{source, span}]  spans are authoritative grounding
   - allowed_edits[], forbidden_edits[]
   - suggested_patch{path, next_value_hint, oracle_kind_hint, rationale}
   - do_not[]
4) Optional raw table-review JSON excerpt (item_findings + evidence_chain)
5) Optional raw script-review / contract_patch excerpt (findings + patch.action)

When TableGenFeedback.items is non-empty, it OUTRANKS raw excerpts.
When Feedback is empty, you MAY derive patch intents from raw excerpts using the
mapping rules below — still no free-form redesign of the whole table.

==============================================================================
HARD BOUNDARIES
==============================================================================
1. Edit ONLY allowed_edits for each item (default: expect, fail_mode,
   expect_confidence). Never touch forbidden_edits (default: call_graph,
   recipe_id, layer, entrypoint) unless Feedback explicitly allows.
2. Do NOT output pytest / test code / patches / Harbor advice.
3. Every patched literal (value, regex, exception name, http_status, message
   substr) MUST appear in Issue text OR in some evidence_digest.span /
   evidence_chain.span_text. If not groundable → unchanged + reason
   insufficient_grounding (do NOT invent).
4. error_type=render_error OR patch.action in {noop_rerender, mark_render_bug}
   OR do_not_edit_contract → do NOT change that must_id; record unchanged.
5. Prefer blocking items. If prefer_blocking_only=true, ignore warning-only
   unless they are required to keep multi_item consistency after a blocking fix.
6. Output ONE JSON object only. No markdown fences.

==============================================================================
PRIORITY ORDER
==============================================================================
1. false_fail / invented_expect (blocking)
2. quote_drift (blocking) when a longer Issue span is provided
3. off_must / recipe_misaligned / script_contract_mismatch (blocking)
4. weak_degraded (blocking if quote has clear literals; else may leave low)
5. multi_item_inconsistency
6. warnings
7. insufficient_evidence → never invent; unchanged

==============================================================================
ERROR_TYPE → REPAIR PLAYBOOK (execute literally)
==============================================================================
false_fail:
  Align expect with evidence_digest Issue/contract contradiction.
  Prefer suggested_patch.next_value_hint if grounded; set oracle_kind from
  oracle_kind_hint or keep prior kind if still valid.
  Typical: required→None means field_path value=null, confidence=high.

off_must:
  Do NOT invent a new call_graph. Only adjust expect/fail_mode/confidence so
  the EXISTING locked call_graph is tested against the primary Must described
  in Issue spans. If impossible without changing call_graph → unchanged +
  reason needs_refill_step2 ( steers upstream, not you).

weak_degraded:
  If evidence_digest shows concrete literals in Issue/quote, upgrade
  oracle_kind to equality/field_path/contains using those literals and set
  expect_confidence=high. If no literals → leave raises/low unchanged.

quote_drift:
  Replace issue_quote ONLY with a longer verbatim Issue substring provided in
  Feedback evidence (must be Issue substring). Then fix expect to match the
  corrected quote. If no replacement span → unchanged.

recipe_misaligned:
  Keep recipe_id/call_graph locked. Fix expect so it exercises the intended
  integration meaning described in recipe/Issue spans (e.g. alias field value),
  not constructor smoke checks. If requires call_graph change → needs_refill_step2.

multi_item_inconsistency:
  Patch the item(s) Feedback names so expects/fail_modes stop contradicting;
  ground using Issue spans.

script_contract_mismatch / invented_expect:
  Reassert contract expect from Issue/Feedback spans (table wins). Remove any
  pressure to keep script-invented literals.

insufficient_evidence:
  unchanged + reason insufficient_evidence.

render_error:
  unchanged + reason render_error.

==============================================================================
RAW EXCERPT MAPPING (only if Feedback.items empty)
==============================================================================
Table-review item_findings:
  issue → error_type; claim → what_is_wrong; evidence_chain[].span_text →
  evidence_digest; fix → rationale / next_value_hint if explicitly stated.

Script-review contract_patch findings:
  patch.action=update_expect → treat as patchable contract error
  patch.action in {noop_rerender, mark_render_bug} → render_error / unchanged
  Prefer evidence_chain steps with source_type script_span + contract_field;
  require issue_span before claiming false_fail.

==============================================================================
REPAIR WORKFLOW
==============================================================================
1. Parse Feedback (or map excerpts).
2. Build worklist: blocking first, dedupe by must_id (keep highest severity /
   highest priority error_type).
3. For each worklist item: apply playbook; emit FULL expect envelope for that
   must_id (all expect keys present; unused null).
4. Keep issue_quote unchanged except quote_drift rule.
5. Do not modify items with no feedback.
6. Self-check flags must be honest.

==============================================================================
OUTPUT JSON SCHEMA
==============================================================================
{
  "action": "patch_contract",
  "patched_must_ids": ["M1-..."],
  "unchanged_must_ids": [
    {"must_id": "M2-...", "reason": "render_error|insufficient_grounding|insufficient_evidence|needs_refill_step2|no_feedback|warning_skipped"}
  ],
  "items_patch": [
    {
      "must_id": "M1-...",
      "source_finding_ref": "TF item must_id / finding_id / F1",
      "error_type_applied": "false_fail",
      "issue_quote": "same as before OR quote_drift replacement",
      "oracle_kind": "equality|field_path|raises|stdout_regex|http_status|contains|predicate_ref",
      "expect": {
        "oracle_kind": "...",
        "value": null,
        "field_path": null,
        "exception": null,
        "regex": null,
        "http_status": null,
        "message_substr": null,
        "compare": "eq"
      },
      "fail_mode": "attr_error|assert|raise|not_implemented|cli_nonzero",
      "expect_confidence": "high|low",
      "repair_note": "<=120 chars; cite evidence span"
    }
  ],
  "fields_touched": ["expect", "fail_mode", "expect_confidence"],
  "self_checks": {
    "only_allowed_edits": true,
    "no_invented_literals": true,
    "no_script_rewrite": true,
    "feedback_driven_only": true
  },
  "summary": "<=200 chars"
}

If Feedback empty AND excerpts empty/unusable:
  action=patch_contract, items_patch=[], summary="no feedback".
""".strip()


CONTRACT_REPAIR_USER = """
Repair the BehaviorContract using reviewer feedback only.
Do not rewrite scripts. Do not freely regenerate the whole table.
Follow ERROR_TYPE playbooks in the system prompt.

## Issue text
{issue_text}

## Current BehaviorContract JSON
{contract_json}

## TableGenFeedback (canonical; prefer this)
{table_gen_feedback_json}

## Optional raw table-review excerpt (use only if Feedback.items is empty)
{table_review_excerpt}

## Optional raw script-review / contract_patch excerpt (use only if Feedback.items is empty)
{script_review_excerpt}

## Repair budget / hints
- max_items_to_patch: {max_items_to_patch}
- prefer_blocking_only: {prefer_blocking_only}
- locked_fields: {locked_fields}
- round_no: {round_no}

## Filler instructions (from Feedback, if any)
{filler_instructions}

Reminders:
1. Blocking false_fail / invented_expect first; render_error → unchanged.
2. Re-emit FULL expect envelopes for every patched must_id.
3. Literals must appear in Issue or evidence spans.
4. JSON only.
""".strip()


def format_contract_repair_user(
    *,
    issue_text: str,
    contract_json: dict[str, Any] | str,
    table_gen_feedback: dict[str, Any] | str | None = None,
    table_review_excerpt: str | dict[str, Any] = "",
    script_review_excerpt: str | dict[str, Any] = "",
    max_items_to_patch: int = 8,
    prefer_blocking_only: bool = True,
    locked_fields: list[str] | None = None,
    round_no: int = 1,
) -> str:
    """Fill the repair user template for the contract repair agent."""
    if table_gen_feedback is None:
        table_gen_feedback = EMPTY_TABLE_GEN_FEEDBACK
    if isinstance(contract_json, dict):
        contract_body = json.dumps(contract_json, ensure_ascii=False, indent=2)
    else:
        contract_body = str(contract_json)
    if isinstance(table_gen_feedback, dict):
        feedback_body = json.dumps(table_gen_feedback, ensure_ascii=False, indent=2)
        filler_instructions = table_gen_feedback.get("filler_instructions") or []
        if isinstance(filler_instructions, list):
            filler_txt = "\n".join(f"- {x}" for x in filler_instructions) or "(none)"
        else:
            filler_txt = str(filler_instructions)
    else:
        feedback_body = str(table_gen_feedback)
        filler_txt = "(none)"
    if isinstance(table_review_excerpt, dict):
        table_excerpt = json.dumps(table_review_excerpt, ensure_ascii=False, indent=2)
    else:
        table_excerpt = (table_review_excerpt or "").strip() or "(none)"
    if isinstance(script_review_excerpt, dict):
        script_excerpt = json.dumps(script_review_excerpt, ensure_ascii=False, indent=2)
    else:
        script_excerpt = (script_review_excerpt or "").strip() or "(none)"
    locks = locked_fields or list(DEFAULT_FORBIDDEN_EDITS)
    return CONTRACT_REPAIR_USER.format(
        issue_text=issue_text.strip() or "(empty issue)",
        contract_json=contract_body,
        table_gen_feedback_json=feedback_body,
        table_review_excerpt=table_excerpt,
        script_review_excerpt=script_excerpt,
        max_items_to_patch=max_items_to_patch,
        prefer_blocking_only=str(prefer_blocking_only).lower(),
        locked_fields=", ".join(locks),
        round_no=round_no,
        filler_instructions=filler_txt,
    )


def build_minimal_feedback_from_table_review(table_review: dict[str, Any]) -> dict[str, Any]:
    """Best-effort map §3.5.8 review JSON → TableGenFeedback (for callers)."""
    items: list[dict[str, Any]] = []
    for finding in table_review.get("item_findings") or []:
        issue = finding.get("issue") or "insufficient_evidence"
        if issue == "ok":
            continue
        chain = finding.get("evidence_chain") or []
        digest = []
        for step in chain:
            span = step.get("span_text") or ""
            src = step.get("source_type") or "derived"
            if src == "issue_span":
                source = "issue"
            elif src == "contract_field":
                source = "contract"
            elif src == "recipe_hint":
                source = "recipe"
            else:
                source = src
            if span:
                digest.append({"source": source, "span": span[:80]})
        severity = finding.get("severity") or (
            "blocking" if issue in {"false_fail", "off_must", "recipe_misaligned"} else "warning"
        )
        items.append(
            {
                "must_id": finding.get("must_id") or "",
                "error_type": issue,
                "severity": severity,
                "what_is_wrong": (finding.get("claim") or finding.get("fix") or "")[:200],
                "evidence_digest": digest,
                "allowed_edits": list(DEFAULT_ALLOWED_EDITS),
                "forbidden_edits": list(DEFAULT_FORBIDDEN_EDITS),
                "suggested_patch": {
                    "path": f"items[must_id={finding.get('must_id')}].expect",
                    "next_value_hint": None,
                    "oracle_kind_hint": "keep",
                    "rationale": (finding.get("fix") or "")[:150],
                },
                "do_not": ["rewrite pytest", "invent numbers not in Issue", "change call_graph freely"],
                "source_finding_ref": finding.get("finding_id") or finding.get("must_id"),
            }
        )
    return {
        "feedback_id": f"TF-from-table-review-{table_review.get('verdict', 'unknown')}",
        "source": "table_review",
        "blocking": bool(table_review.get("blocking"))
        or any(i.get("severity") == "blocking" for i in items),
        "summary_for_filler": (table_review.get("summary") or "repair from table review")[:200],
        "items": items,
        "filler_instructions": list(EMPTY_TABLE_GEN_FEEDBACK["filler_instructions"]),
    }
