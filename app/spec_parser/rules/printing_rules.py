"""Printing-family AST enrichment rules."""

from __future__ import annotations

import re
from pathlib import Path

from app.knowledge.contract_features import ContractFeatureSet, extract_from_issue
from app.spec_parser.rules.common_rules import PRINTING_TARGET_FILES, SYMPY_TYPE_TO_HANDLER
from app.spec_parser.schema import RepoEnrichment
from app.spec_parser.visitors.return_shape import ReturnShapeVisitor, index_class_methods
from app.task import Task


def _resolve_printing_files(task: Task) -> list[Path]:
    root = Path(task.project_path)
    found: list[Path] = []
    for rel in PRINTING_TARGET_FILES:
        p = root / rel
        if p.is_file():
            found.append(p)
    if not found:
        for p in root.rglob("ccode.py"):
            if "printing" in str(p):
                found.append(p)
                break
    return found


def _callees_from_issue(issue_text: str) -> set[str]:
    fs = extract_from_issue(issue_text)
    if fs is None:
        names: set[str] = set()
        for m in re.finditer(r"\b(ccode|sinc|Ne|Eq|Piecewise)\b", issue_text):
            names.add(m.group(1))
        return names
    return set(fs.callees) | {
        t for t in SYMPY_TYPE_TO_HANDLER if t.lower() in issue_text.lower()
    }


def enrich(
    task: Task,
    issue_text: str,
    issue_fs: ContractFeatureSet | None,
    target_files: list[Path] | None = None,
) -> RepoEnrichment:
    files = target_files or _resolve_printing_files(task)
    existing_handlers: set[str] = set()
    neighbor_reference: str | None = None
    snippets: dict[str, str] = {}

    for fpath in files:
        source = fpath.read_text(errors="replace")
        methods = index_class_methods(source, "CCodePrinter")
        if not methods:
            methods = index_class_methods(source)
        for name in methods:
            if name.startswith("_print_"):
                existing_handlers.add(name)

        for mname, lineno in methods.items():
            if not mname.startswith("_print_"):
                continue
            try:
                tree = __import__("ast").parse(source)
            except SyntaxError:
                continue
            for node in __import__("ast").walk(tree):
                if (
                    isinstance(node, __import__("ast").FunctionDef)
                    and node.name == mname
                ):
                    vis = ReturnShapeVisitor()
                    vis.visit(node)
                    if vis.features.has_self_print_return and vis.features.has_ast_compose:
                        neighbor_reference = mname
                        snippets[mname] = source.splitlines()[lineno - 1 : lineno + 3]
                        break

    issue_callees = _callees_from_issue(issue_text)
    needed_handlers: set[str] = set()
    for callee in issue_callees:
        h = SYMPY_TYPE_TO_HANDLER.get(callee)
        if h and h.startswith("_print_"):
            needed_handlers.add(h)
    if "sinc" in issue_text.lower():
        needed_handlers.add("_print_sinc")
    if re.search(r"\bNe\b|\bEq\b|Relational", issue_text):
        needed_handlers.add("_print_Relational")

    missing = sorted(h for h in needed_handlers if h not in existing_handlers)
    hints = sorted(needed_handlers | existing_handlers)

    return RepoEnrichment(
        target_files=[str(f.relative_to(task.project_path)) for f in files],
        missing_handlers=missing,
        co_fix_candidates=[],
        neighbor_reference=neighbor_reference or "_print_ITE",
        architecture_pattern="delegate_ast" if neighbor_reference else "unknown",
        negative_patterns=["inline_c_ternary_pattern"] if missing else [],
        search_api_hints=[h for h in hints if h.startswith("_print_")][:10],
        evidence_snippets={
            k: "\n".join(v) for k, v in snippets.items()
        },
    )
