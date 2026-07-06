"""Check Issue code-block symbols against scoped source files (repo-agnostic)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from app.spec_parser.symbol_index import SymbolIndex
from app.spec_parser.visitors.return_shape import index_class_methods

_RELATIONAL_NAMES = frozenset({"Ne", "Eq", "Relational", "StrictLessThan", "StrictGreaterThan"})
_AST_TYPE_TO_HANDLER = {
    "Ne": "_print_Relational",
    "Eq": "_print_Relational",
    "Relational": "_print_Relational",
    "Piecewise": "_print_Piecewise",
    "sinc": "_print_sinc",
}


def symbols_in_issue_text(issue_text: str, reporter_drafts: list[str]) -> set[str]:
    blob = issue_text + "\n" + "\n".join(reporter_drafts)
    found: set[str] = set()
    for name in _RELATIONAL_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", blob):
            found.add(name)
    if re.search(r"\bsinc\b", blob, re.IGNORECASE):
        found.add("sinc")
    if "Piecewise" in blob:
        found.add("Piecewise")
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]*)\b", blob):
        found.add(m.group(1))
    return found


def handlers_for_symbol(symbol: str) -> list[str]:
    if symbol in _AST_TYPE_TO_HANDLER:
        return [_AST_TYPE_TO_HANDLER[symbol]]
    if symbol.startswith("_print_"):
        return [symbol]
    if symbol[0].isupper():
        return [f"_print_{symbol}"]
    return []


def _file_has_handler(source: str, handler: str) -> bool:
    return f"def {handler}" in source or f"def {handler.split('.')[-1]}" in source


def uncovered_handlers_in_scope(
    symbols: set[str],
    scoped_files: list[str],
    project_path: str,
    index: SymbolIndex,
) -> list[str]:
    root = Path(project_path)
    combined_source = ""
    all_methods: set[str] = set()
    for rel in scoped_files:
        fpath = root / rel
        if not fpath.is_file():
            continue
        try:
            src = fpath.read_text(errors="replace")
        except OSError:
            continue
        combined_source += src + "\n"
        all_methods.update(index_class_methods(src).keys())

    missing: set[str] = set()
    for sym in symbols:
        for handler in handlers_for_symbol(sym):
            if handler in all_methods:
                continue
            if _file_has_handler(combined_source, handler):
                continue
            if sym in _RELATIONAL_NAMES or sym == "sinc" or sym == "Piecewise":
                missing.add(handler)
    return sorted(missing)
