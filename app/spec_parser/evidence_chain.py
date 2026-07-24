"""v3.3 Issue↔AC evidence-chain helpers."""

from __future__ import annotations

from typing import Any

from app.spec_parser.schema import IssueCoverageChain, IssueCoverageItem, ReviewIssueGap


def summarize_coverage(items: list[IssueCoverageItem]) -> dict[str, int]:
    summary = {"covered": 0, "partial": 0, "missing": 0, "over_spec": 0, "deferred": 0}
    for item in items:
        key = (item.verdict or "missing").lower()
        if key not in summary:
            key = "partial"
        summary[key] = summary.get(key, 0) + 1
    return summary


def migrate_alignment_to_chain(
    gaps: list[ReviewIssueGap],
) -> list[IssueCoverageItem]:
    """Best-effort migration when reviewer only emits issue_alignment."""
    out: list[IssueCoverageItem] = []
    for i, gap in enumerate(gaps):
        kind = (gap.kind or "").lower()
        if kind == "missing_must":
            verdict, strength = "missing", "missing"
        elif kind == "weak_assert":
            verdict, strength = "partial", "weak"
        elif kind == "over_spec_risk":
            verdict, strength = "over_spec", "medium"
        else:
            verdict, strength = "partial", "unknown"
        if gap.superseded_by_blocking:
            verdict = "deferred"
        out.append(
            IssueCoverageItem(
                issue_item_id=f"align-{i + 1}",
                issue_quote=gap.detail[:200],
                ac_id=None,
                assertion_strength=strength,
                evidence_type="none",
                verdict=verdict,
                legal_rewrite="" if gap.superseded_by_blocking else gap.legal_rewrite,
            )
        )
    return out


def parse_coverage_items(raw: Any) -> list[IssueCoverageItem]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    out: list[IssueCoverageItem] = []
    for item in raw:
        if isinstance(item, dict):
            try:
                out.append(IssueCoverageItem.model_validate(item))
            except Exception:  # noqa: BLE001
                continue
        elif isinstance(item, IssueCoverageItem):
            out.append(item)
    return out


def sanitize_coverage_items(
    items: list[IssueCoverageItem],
    *,
    is_illegal_rewrite,
) -> tuple[list[IssueCoverageItem], list[str], bool]:
    """Drop illegal rewrites; demote covered+weak to partial."""
    kept: list[IssueCoverageItem] = []
    deferred: list[str] = []
    changed = False
    weak_strengths = {"weak", "existence", "stub"}
    for item in items:
        updates: dict[str, Any] = {}
        if item.legal_rewrite and is_illegal_rewrite(item.legal_rewrite):
            updates["legal_rewrite"] = ""
            updates["verdict"] = "deferred"
            deferred.append(
                f"dropped illegal coverage rewrite for {item.issue_item_id or item.ac_id}"
            )
            changed = True
        strength = (item.assertion_strength or "").lower()
        verdict = (updates.get("verdict") or item.verdict or "").lower()
        if verdict == "covered" and strength in weak_strengths:
            updates["verdict"] = "partial"
            changed = True
        if updates:
            kept.append(item.model_copy(update=updates))
        else:
            kept.append(item)
    return kept, deferred, changed


def build_coverage_chain(
    items: list[IssueCoverageItem],
    *,
    round_no: int,
    stage: str,
    source: str = "reviewer_llm",
) -> IssueCoverageChain:
    stage_lit = stage if stage in ("preflight", "gate", "post_pass") else "preflight"
    return IssueCoverageChain(
        round_no=round_no,
        stage=stage_lit,  # type: ignore[arg-type]
        items=items,
        summary=summarize_coverage(items),
        source=source,
    )


def coverage_priority_actions(items: list[IssueCoverageItem], *, limit: int = 5) -> list[str]:
    """Ordered actions for generator: missing → wrong_layer → weak."""
    missing = [
        it
        for it in items
        if (it.verdict or "").lower() == "missing"
        or (it.assertion_strength or "").lower() == "missing"
    ]
    wrong = [
        it
        for it in items
        if (it.assertion_strength or "").lower() == "wrong_layer"
    ]
    weak = [
        it
        for it in items
        if (it.assertion_strength or "").lower() in ("weak", "existence", "stub")
        and (it.verdict or "").lower() == "partial"
    ]
    actions: list[str] = []
    for it in missing + wrong + weak:
        label = it.issue_item_id or it.ac_id or "?"
        quote = (it.issue_quote or "")[:80]
        line = f"Cover Issue {label} ({it.verdict}/{it.assertion_strength}): {quote}"
        if it.legal_rewrite:
            line += f"\n  legal_rewrite: {it.legal_rewrite}"
        actions.append(line)
        if len(actions) >= limit:
            break
    return actions
