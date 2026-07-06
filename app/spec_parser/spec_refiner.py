"""Merge LLM draft spec with static repo enrichment."""

from __future__ import annotations

from app import config
from app.spec_parser.schema import (
    NegativeConstraint,
    RepoEnrichment,
    StructuredSpecification,
)


def _is_actionable_handler(label: str) -> bool:
    return (
        label.startswith("_")
        or label.endswith(".py")
        or "/" in label
        or "." in label
    )


def _rank_co_fix(candidates: list[str], enrichment: RepoEnrichment) -> list[str]:
    target_set = set(enrichment.target_files[:3])
    ranked: list[tuple[int, str]] = []
    for c in candidates:
        score = 0
        if c in enrichment.search_api_hints[:10]:
            score += 1
        if any(c in enrichment.evidence_snippets for _ in enrichment.evidence_snippets):
            score += 2
        if enrichment.context_domain and enrichment.context_domain in c:
            score += 1
        if target_set:
            score += 1
        ranked.append((score, c))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [c for _, c in ranked]


def merge(
    draft: StructuredSpecification,
    enrichment: RepoEnrichment | None,
) -> StructuredSpecification:
    if enrichment is None:
        return draft

    spec = draft.model_copy(deep=True)
    spec.repo_enrichment = enrichment

    fs = spec.fix_scope.model_copy(deep=True)
    for handler in enrichment.missing_handlers:
        if not _is_actionable_handler(handler):
            continue
        label = handler
        if handler.startswith("_print_") and "." not in handler:
            label = f"*.{handler}"
        if label not in fs.in_scope and handler not in fs.in_scope:
            fs.in_scope.append(handler)

    ranked = _rank_co_fix(enrichment.co_fix_candidates, enrichment)
    max_co = config.spec_parser_max_co_fix
    for candidate in ranked[:max_co]:
        if candidate not in fs.co_fix_required:
            fs.co_fix_required.append(candidate)

    for prereq in enrichment.missing_handlers:
        if prereq.startswith("_print_") and prereq not in fs.prerequisite:
            if any(
                tok in prereq
                for tok in ("Relational", "Piecewise", "sinc")
            ):
                fs.prerequisite.append(prereq)

    spec.fix_scope = fs

    ah = spec.architecture_hint.model_copy(deep=True)
    if enrichment.neighbor_reference and not ah.neighbor_reference:
        ah.neighbor_reference = enrichment.neighbor_reference
    if enrichment.architecture_pattern != "unknown":
        pattern_map = {
            "guard": ("guard", "minimal_guard"),
            "delegate": ("delegate_chain", "delegate_ast"),
            "delegate_ast": ("delegate_chain", "delegate_ast"),
            "loop_clamp": ("dimension_clamp", "dimension_clamp"),
            "dimension_clamp": ("dimension_clamp", "dimension_clamp"),
        }
        layer, pattern = pattern_map.get(
            enrichment.architecture_pattern, (ah.layer, ah.pattern)
        )
        if ah.layer == "unknown":
            ah.layer = layer  # type: ignore[assignment]
        if ah.pattern == "unknown":
            ah.pattern = pattern  # type: ignore[assignment]
    spec.architecture_hint = ah

    if enrichment.negative_patterns:
        for pat in enrichment.negative_patterns:
            desc = f"Avoid pattern: {pat}"
            if not any(nc.description == desc for nc in spec.negative_constraints):
                spec.negative_constraints.append(
                    NegativeConstraint(
                        description=desc,
                        rationale="Detected by static AST analysis",
                    )
                )

    return spec
