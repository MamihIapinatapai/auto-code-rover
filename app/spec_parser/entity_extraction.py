"""Collect query entities from P1 draft and issue text (deterministic)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.knowledge.contract_features import extract_from_issue
from app.spec_parser.entity_policy import (
    ISSUE_CLASS_STOPLIST,
    bound_method_name,
    is_ambiguous_method,
    normalize_fix_scope_label,
)
from app.spec_parser.schema import StructuredSpecification
from app.spec_parser.symbol_index import SymbolIndex

STOPLIST = frozenset(
    {
        "valueerror",
        "typeerror",
        "assertionerror",
        "exception",
        "error",
        "true",
        "false",
        "none",
        "sympy",
        "test",
        "issue",
        "bug",
        "fix",
        "pass",
        "fail",
    }
)

PATH_RE = re.compile(r"(?:[\w.-]+/)+[\w.-]+\.py")
IDENT_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\b")
CALL_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*\(", re.IGNORECASE)


@dataclass
class EntityQuery:
    name: str
    kind: str  # class | method | api | file_path
    source: str
    weight: float = 1.0
    is_primary: bool = False


@dataclass
class EntityQuerySet:
    queries: list[EntityQuery] = field(default_factory=list)

    def names(self) -> list[str]:
        return [q.name for q in self.queries]


def _add(queries: dict[tuple[str, str], EntityQuery], q: EntityQuery) -> None:
    key = (q.name.lower(), q.kind)
    existing = queries.get(key)
    if existing is None or q.weight > existing.weight:
        queries[key] = q
    elif existing is not None and q.is_primary and not existing.is_primary:
        queries[key] = EntityQuery(
            name=existing.name,
            kind=existing.kind,
            source=existing.source,
            weight=existing.weight,
            is_primary=True,
        )


def _normalize_entity(raw: str) -> tuple[str, str | None]:
    text = raw.strip()
    if not text:
        return "", None
    lower = text.lower()
    if lower.endswith(" constructor"):
        return text[: -len(" constructor")].strip(), "__init__"
    text = normalize_fix_scope_label(text)
    lower = text.lower()
    if "." in text and not text.endswith(".py"):
        parts = text.split(".")
        if len(parts) == 2:
            return parts[0], parts[1]
    return text, None


def _add_class_and_bound_method(
    queries: dict[tuple[str, str], EntityQuery],
    class_name: str,
    method: str | None,
    *,
    source: str,
    weight: float,
    is_primary: bool = False,
) -> None:
    _add(
        queries,
        EntityQuery(
            name=class_name,
            kind="class",
            source=source,
            weight=weight,
            is_primary=is_primary,
        ),
    )
    if method and is_ambiguous_method(method):
        _add(
            queries,
            EntityQuery(
                name=bound_method_name(class_name, method),
                kind="method",
                source=f"{source}_bound",
                weight=weight * 1.05,
                is_primary=is_primary,
            ),
        )
    elif method:
        _add(
            queries,
            EntityQuery(
                name=method,
                kind="method",
                source=source,
                weight=weight * 0.95,
                is_primary=is_primary,
            ),
        )


def infer_primary_class(
    entities: EntityQuerySet, draft: StructuredSpecification
) -> str | None:
    for q in entities.queries:
        if q.is_primary and q.kind == "class":
            return q.name
    if draft.failure_anchor and draft.failure_anchor.named_entities:
        for raw in draft.failure_anchor.named_entities:
            name, _ = _normalize_entity(raw)
            if name and name[0].isupper() and name.lower() not in STOPLIST:
                return name.split(".")[0]
    for ac in draft.acceptance_criteria:
        if ac.priority == "must" and ac.covers_entity:
            name, _ = _normalize_entity(ac.covers_entity)
            if name and name[0].isupper():
                return name.split(".")[0]
    return None


def collect_entities(
    issue_text: str,
    draft: StructuredSpecification,
    index: SymbolIndex | None = None,
) -> EntityQuerySet:
    queries: dict[tuple[str, str], EntityQuery] = {}
    primary_names: set[str] = set()
    if draft.failure_anchor and draft.failure_anchor.named_entities:
        name, _ = _normalize_entity(draft.failure_anchor.named_entities[0])
        if name:
            primary_names.add(name.split(".")[0])

    if draft.failure_anchor:
        for i, raw in enumerate(draft.failure_anchor.named_entities):
            name, method = _normalize_entity(raw)
            if not name or name.lower() in STOPLIST:
                continue
            is_primary = i == 0 or name.split(".")[0] in primary_names
            _add_class_and_bound_method(
                queries,
                name.split(".")[0],
                method,
                source="p1_named",
                weight=1.0,
                is_primary=is_primary,
            )

    for ac in draft.acceptance_criteria:
        if not ac.covers_entity:
            continue
        name, method = _normalize_entity(ac.covers_entity)
        if name and name.lower() not in STOPLIST:
            is_primary = ac.priority == "must" and (
                name.split(".")[0] in primary_names or name in primary_names
            )
            if name.startswith("_"):
                _add(
                    queries,
                    EntityQuery(
                        name=name,
                        kind="method",
                        source="p1_covers",
                        weight=0.95,
                        is_primary=is_primary,
                    ),
                )
            else:
                _add_class_and_bound_method(
                    queries,
                    name.split(".")[0],
                    method,
                    source="p1_covers",
                    weight=0.9,
                    is_primary=is_primary,
                )

    for label in (
        draft.fix_scope.in_scope
        + draft.fix_scope.co_fix_required
        + draft.fix_scope.prerequisite
    ):
        name, method = _normalize_entity(label)
        if name and name.lower() not in STOPLIST:
            if name.startswith("_") or name.endswith(".py"):
                _add(
                    queries,
                    EntityQuery(
                        name=name,
                        kind="method" if name.startswith("_") else "file_path",
                        source="p1_fix_scope",
                        weight=0.85,
                    ),
                )
            else:
                _add_class_and_bound_method(
                    queries,
                    name.split(".")[0],
                    method,
                    source="p1_fix_scope",
                    weight=0.85,
                )

    for path in PATH_RE.findall(issue_text):
        _add(
            queries,
            EntityQuery(
                name=path.replace("\\", "/"),
                kind="file_path",
                source="issue_path",
                weight=1.0,
            ),
        )

    issue_fs = extract_from_issue(issue_text)
    if issue_fs:
        for callee in issue_fs.callees:
            if callee.lower() not in STOPLIST:
                _add(
                    queries,
                    EntityQuery(
                        name=callee,
                        kind="api",
                        source="issue_codeblock",
                        weight=0.8,
                    ),
                )

    for m in CALL_RE.finditer(issue_text):
        name = m.group(1)
        if name.lower() not in STOPLIST and len(name) > 2:
            _add(
                queries,
                EntityQuery(
                    name=name, kind="api", source="issue_regex", weight=0.7
                ),
            )

    for m in IDENT_RE.finditer(issue_text):
        name = m.group(1)
        if name.lower() in STOPLIST or name.lower() in ISSUE_CLASS_STOPLIST:
            continue
        if index is not None:
            from app import config

            if (
                config.spec_parser_require_class_in_index_for_issue_class
                and name not in index.classes
            ):
                continue
        _add(
            queries,
            EntityQuery(
                name=name, kind="class", source="issue_class", weight=0.6
            ),
        )

    return EntityQuerySet(queries=list(queries.values()))
