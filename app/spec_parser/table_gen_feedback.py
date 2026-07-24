"""TableGenFeedback merge/apply for contract repair (v3.4)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.spec_parser.behavior_contract import validate_contract

_ALLOWED_DEFAULT = frozenset(
    {"expect", "fail_mode", "expect_confidence", "issue_quote", "oracle_kind"}
)
_FORBIDDEN_DEFAULT = frozenset(
    {"call_graph", "recipe_id", "layer", "entrypoint", "must_id"}
)

_ERROR_PRIORITY = {
    "false_fail": 0,
    "invented_expect": 1,
    "quote_drift": 2,
    "off_must": 3,
    "recipe_misaligned": 4,
    "script_contract_mismatch": 5,
    "weak_degraded": 6,
    "multi_item_inconsistency": 7,
    "insufficient_evidence": 8,
    "render_error": 9,
}


def empty_feedback(*, source: str = "merged") -> dict[str, Any]:
    return {
        "feedback_id": "",
        "source": source,
        "blocking": False,
        "summary_for_filler": "",
        "items": [],
        "filler_instructions": [],
    }


def merge_feedback(
    table_review: dict | None,
    script_patch: dict | None,
) -> dict[str, Any]:
    items: list[dict] = []
    for src_name, blob in (
        ("table_review", table_review),
        ("script_review", script_patch),
    ):
        if not blob:
            continue
        for it in blob.get("items") or blob.get("findings") or []:
            row = deepcopy(it)
            row.setdefault("error_type", row.get("problem") or "script_contract_mismatch")
            row.setdefault("severity", "blocking" if blob.get("blocking") else "warning")
            items.append(row)

    # dedupe must_id + error_type
    best: dict[tuple[str, str], dict] = {}
    for it in items:
        key = (str(it.get("must_id") or ""), str(it.get("error_type") or ""))
        prev = best.get(key)
        if prev is None:
            best[key] = it
            continue
        # keep longer evidence
        def _elen(x: dict) -> int:
            return len(str(x.get("evidence_digest") or x.get("evidence_chain") or ""))

        if _elen(it) >= _elen(prev):
            # severity: blocking wins
            if prev.get("severity") == "blocking":
                it["severity"] = "blocking"
            best[key] = it
        elif it.get("severity") == "blocking":
            prev["severity"] = "blocking"

    merged_items = sorted(
        best.values(),
        key=lambda x: _ERROR_PRIORITY.get(str(x.get("error_type")), 99),
    )
    # render_error stays but not editable
    blocking = any(i.get("severity") == "blocking" for i in merged_items)
    return {
        "feedback_id": "merged",
        "source": "merged",
        "blocking": blocking,
        "summary_for_filler": (table_review or script_patch or {}).get("summary")
        or (table_review or script_patch or {}).get("summary_for_filler")
        or "",
        "items": merged_items,
        "filler_instructions": list(
            (table_review or {}).get("filler_instructions") or []
        ),
    }


def _set_path(obj: dict, path: str, value: Any) -> None:
    """Support paths like items[must_id=M1].expect.value or items.0.expect.value."""
    if path.startswith("items[must_id="):
        mid = path.split("items[must_id=", 1)[1].split("]", 1)[0]
        rest = path.split("].", 1)[1] if "]." in path else ""
        for it in obj.get("items") or []:
            if str(it.get("must_id")) == mid:
                cur: Any = it
                parts = rest.split(".") if rest else []
                for p in parts[:-1]:
                    if p not in cur or not isinstance(cur[p], dict):
                        cur[p] = {}
                    cur = cur[p]
                if parts:
                    cur[parts[-1]] = value
                return
        return
    # items.N.field...
    parts = path.split(".")
    cur: Any = obj
    for p in parts[:-1]:
        if p == "items":
            continue
        if p.isdigit():
            cur = obj["items"][int(p)]
            continue
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    if parts:
        last = parts[-1]
        if last.isdigit():
            return
        cur[last] = value


def apply_items_patch(
    contract: dict[str, Any],
    repair_json: dict[str, Any],
    *,
    issue_text: str = "",
    recipe_cards: dict | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply whitelist patches; rollback if validate_contract fails.

    Returns (new_contract, apply_report).
    """
    original = deepcopy(contract)
    updated = deepcopy(contract)
    applied: list[str] = []
    skipped: list[str] = []

    patches = repair_json.get("items_patch") or repair_json.get("patches") or []
    if isinstance(repair_json.get("items"), list) and not patches:
        # full items replace for matching must_ids (only allowed fields)
        by_id = {str(i.get("must_id")): i for i in updated.get("items") or []}
        for inc in repair_json["items"]:
            mid = str(inc.get("must_id") or "")
            if mid not in by_id:
                skipped.append(mid)
                continue
            target = by_id[mid]
            for k, v in inc.items():
                if k in _FORBIDDEN_DEFAULT and k not in (inc.get("allowed_edits") or []):
                    skipped.append(f"{mid}.{k}")
                    continue
                if k in _ALLOWED_DEFAULT or k in (inc.get("allowed_edits") or []):
                    target[k] = v
                    applied.append(f"{mid}.{k}")
    else:
        for p in patches:
            et = str(p.get("error_type") or "")
            if et == "render_error":
                skipped.append("render_error")
                continue
            path = str(p.get("path") or p.get("suggested_patch", {}).get("path") or "")
            val = p.get("next_value")
            if val is None:
                val = (p.get("suggested_patch") or {}).get("next_value_hint")
            allowed = set(p.get("allowed_edits") or _ALLOWED_DEFAULT)
            field = path.split(".")[-1] if path else ""
            if field and field not in allowed and not path.endswith("expect.value"):
                if not any(a in path for a in allowed):
                    skipped.append(path or field)
                    continue
            if path:
                _set_path(updated, path, val)
                applied.append(path)

    report = validate_contract(
        updated, issue_text=issue_text, recipe_cards=recipe_cards
    )
    if not report["passed"]:
        return original, {
            "ok": False,
            "rolled_back": True,
            "applied": applied,
            "skipped": skipped,
            "validate": report,
        }
    return updated, {
        "ok": True,
        "rolled_back": False,
        "applied": applied,
        "skipped": skipped,
        "validate": report,
    }


def apply_contract_patch(
    contract: dict[str, Any],
    scc_patch: dict[str, Any],
    *,
    issue_text: str = "",
    recipe_cards: dict | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map SCC findings to repair intents."""
    repair_items = []
    for finding in scc_patch.get("findings") or []:
        if finding.get("rule_id") == "SCC-01" or (
            (finding.get("patch") or {}).get("action") in ("noop_rerender", "mark_render_bug")
        ):
            continue
        patch = finding.get("patch") or {}
        if patch.get("action") in ("update_expect", "update_fail_mode", "update_confidence"):
            repair_items.append(
                {
                    "must_id": finding.get("must_id"),
                    "error_type": finding.get("problem") or "script_contract_mismatch",
                    "path": patch.get("path"),
                    "next_value": patch.get("next_value"),
                    "allowed_edits": list(_ALLOWED_DEFAULT),
                }
            )
    return apply_items_patch(
        contract,
        {"items_patch": repair_items},
        issue_text=issue_text,
        recipe_cards=recipe_cards,
    )
