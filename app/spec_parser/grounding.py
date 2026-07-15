"""Issue-first grounding for co_fix / prerequisite scope items (v3.0.2)."""

from __future__ import annotations

from app import config
from app.spec_parser.schema import AcceptanceCriterion, StructuredSpecification


def _grounding_blob(
    issue_text: str,
    acceptance_criteria: list[AcceptanceCriterion],
) -> str:
    parts = [issue_text]
    for ac in acceptance_criteria:
        parts.append(ac.observable)
        if ac.covers_entity:
            parts.append(ac.covers_entity)
        parts.append(ac.description)
    return " ".join(parts).lower()


def is_grounded_in_issue(
    name: str,
    issue_text: str,
    acceptance_criteria: list[AcceptanceCriterion],
) -> bool:
    if not name.strip():
        return False
    return name.lower() in _grounding_blob(issue_text, acceptance_criteria)


def split_grounded_scope_items(
    items: list[str],
    issue_text: str,
    acceptance_criteria: list[AcceptanceCriterion],
) -> tuple[list[str], list[str]]:
    """Return (grounded, hints) — only grounded items are script hard requirements."""
    grounded: list[str] = []
    hints: list[str] = []
    for item in items:
        if is_grounded_in_issue(item, issue_text, acceptance_criteria):
            grounded.append(item)
        else:
            hints.append(item)
    return grounded, hints


def enforceable_co_fix(
    spec: StructuredSpecification,
    issue_text: str = "",
) -> list[str]:
    """co_fix items the script generator / gate must cover (v3: Issue-echo only)."""
    items = list(spec.fix_scope.co_fix_required)
    if not getattr(config, "spec_parser_use_v3_prompts", False):
        return items
    grounded, _ = split_grounded_scope_items(
        items, issue_text, spec.acceptance_criteria
    )
    return grounded


def enforceable_prerequisite(
    spec: StructuredSpecification,
    issue_text: str = "",
) -> list[str]:
    if not getattr(config, "spec_parser_use_v3_prompts", False):
        return list(spec.fix_scope.prerequisite)
    grounded, _ = split_grounded_scope_items(
        spec.fix_scope.prerequisite, issue_text, spec.acceptance_criteria
    )
    return grounded
