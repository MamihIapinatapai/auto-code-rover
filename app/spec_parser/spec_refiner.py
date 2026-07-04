"""Merge LLM draft spec with static repo enrichment."""

from __future__ import annotations

from app.spec_parser.schema import (
    NegativeConstraint,
    RepoEnrichment,
    StructuredSpecification,
)


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
        label = handler
        if handler.startswith("_print_") and "." not in handler:
            label = f"*.{handler}"
        if label not in fs.in_scope and handler not in fs.in_scope:
            fs.in_scope.append(handler)

    for candidate in enrichment.co_fix_candidates:
        if candidate not in fs.co_fix_required:
            fs.co_fix_required.append(candidate)

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
