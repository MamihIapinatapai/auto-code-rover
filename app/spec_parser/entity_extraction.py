"""Collect query entities from P1 draft and issue text (deterministic)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.knowledge.contract_features import extract_from_issue
from app.spec_parser.schema import StructuredSpecification

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


@dataclass
class EntityQuerySet:
    queries: list[EntityQuery] = field(default_factory=list)

    def names(self) -> list[str]:
        return [q.name for q in self.queries]


def _add(queries: dict[str, EntityQuery], q: EntityQuery) -> None:
    key = (q.name.lower(), q.kind)
    existing = queries.get(key)
    if existing is None or q.weight > existing.weight:
        queries[key] = q


def _normalize_entity(raw: str) -> tuple[str, str | None]:
    text = raw.strip()
    if not text:
        return "", None
    lower = text.lower()
    if lower.endswith(" constructor"):
        return text[: -len(" constructor")].strip(), "__init__"
    if "." in text and not text.endswith(".py"):
        parts = text.split(".")
        if len(parts) == 2:
            return parts[0], parts[1]
    return text, None


def collect_entities(
    issue_text: str, draft: StructuredSpecification
) -> EntityQuerySet:
    queries: dict[tuple[str, str], EntityQuery] = {}

    if draft.failure_anchor:
        for raw in draft.failure_anchor.named_entities:
            name, method = _normalize_entity(raw)
            if not name or name.lower() in STOPLIST:
                continue
            _add(
                queries,
                EntityQuery(name=name, kind="class", source="p1_named", weight=1.0),
            )
            if method:
                _add(
                    queries,
                    EntityQuery(
                        name=method, kind="method", source="p1_named", weight=0.95
                    ),
                )

    for ac in draft.acceptance_criteria:
        if not ac.covers_entity:
            continue
        name, method = _normalize_entity(ac.covers_entity)
        if name and name.lower() not in STOPLIST:
            kind = "method" if name.startswith("_") or method else "class"
            if method:
                kind = "method"
                _add(
                    queries,
                    EntityQuery(
                        name=method, kind="method", source="p1_covers", weight=0.95
                    ),
                )
            _add(
                queries,
                EntityQuery(name=name, kind=kind, source="p1_covers", weight=0.9),
            )

    for label in (
        draft.fix_scope.in_scope
        + draft.fix_scope.co_fix_required
        + draft.fix_scope.prerequisite
    ):
        name, method = _normalize_entity(label)
        if name and name.lower() not in STOPLIST:
            kind = "method" if name.startswith("_") or "(" in label else "class"
            _add(
                queries,
                EntityQuery(name=name, kind=kind, source="p1_fix_scope", weight=0.85),
            )
        if method:
            _add(
                queries,
                EntityQuery(
                    name=method, kind="method", source="p1_fix_scope", weight=0.85
                ),
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
                        name=callee, kind="api", source="issue_codeblock", weight=0.8
                    ),
                )

    for m in CALL_RE.finditer(issue_text):
        name = m.group(1)
        if name.lower() not in STOPLIST and len(name) > 2:
            _add(
                queries,
                EntityQuery(name=name, kind="api", source="issue_regex", weight=0.7),
            )

    for m in IDENT_RE.finditer(issue_text):
        name = m.group(1)
        if name.lower() not in STOPLIST:
            _add(
                queries,
                EntityQuery(name=name, kind="class", source="issue_class", weight=0.6),
            )

    return EntityQuerySet(queries=list(queries.values()))
