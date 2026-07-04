"""Build class/function symbol index for a Python project."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app import config
from app.search.search_utils import find_python_files, is_test_file


@dataclass
class SymbolLocation:
    rel_path: str
    lineno: int
    kind: str  # class | function


@dataclass
class SymbolIndex:
    classes: dict[str, list[SymbolLocation]] = field(default_factory=dict)
    functions: dict[str, list[SymbolLocation]] = field(default_factory=dict)
    file_methods: dict[str, list[str]] = field(default_factory=dict)

    def methods_in_file(self, rel_path: str) -> list[str]:
        return self.file_methods.get(rel_path, [])


def _index_file(project_path: Path, abs_path: str) -> tuple[dict, dict, dict]:
    rel = str(Path(abs_path).relative_to(project_path)).replace("\\", "/")
    if is_test_file(rel):
        return {}, {}, {}
    try:
        source = Path(abs_path).read_text(errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, OSError):
        return {}, {}, {}

    classes: dict[str, list[SymbolLocation]] = {}
    functions: dict[str, list[SymbolLocation]] = {}
    methods: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            classes.setdefault(node.name, []).append(
                SymbolLocation(rel_path=rel, lineno=node.lineno, kind="class")
            )
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.setdefault(item.name, []).append(
                        SymbolLocation(rel_path=rel, lineno=item.lineno, kind="function")
                    )
                    functions.setdefault(f"{node.name}.{item.name}", []).append(
                        SymbolLocation(rel_path=rel, lineno=item.lineno, kind="function")
                    )
                    methods.append(item.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.setdefault(node.name, []).append(
                SymbolLocation(rel_path=rel, lineno=node.lineno, kind="function")
            )
            methods.append(node.name)

    file_methods = {rel: sorted(set(methods))}
    return classes, functions, file_methods


def build_symbol_index(project_path: str) -> SymbolIndex:
    root = Path(project_path)
    if not root.is_dir():
        return SymbolIndex()

    cache_key = (str(root.resolve()), config.spec_parser_symbol_index_cache)
    if config.spec_parser_symbol_index_cache:
        return _build_symbol_index_cached(str(root.resolve()))

    return _build_symbol_index_impl(root)


@lru_cache(maxsize=8)
def _build_symbol_index_cached(project_path: str) -> SymbolIndex:
    return _build_symbol_index_impl(Path(project_path))


def _build_symbol_index_impl(root: Path) -> SymbolIndex:
    idx = SymbolIndex()
    py_files = find_python_files(str(root))
    for abs_path in py_files:
        classes, functions, file_methods = _index_file(root, abs_path)
        for name, locs in classes.items():
            idx.classes.setdefault(name, []).extend(locs)
        for name, locs in functions.items():
            idx.functions.setdefault(name, []).extend(locs)
        for rel, ms in file_methods.items():
            idx.file_methods.setdefault(rel, []).extend(ms)
            idx.file_methods[rel] = sorted(set(idx.file_methods[rel]))
    return idx
