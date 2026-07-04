"""Run generic AST visitors and produce RepoEnrichment."""

from __future__ import annotations

import ast
from pathlib import Path

from app.spec_parser.schema import AnalysisScope, RepoEnrichment, StructuredSpecification
from app.spec_parser.scope_compiler import (
    VISITOR_DELEGATE,
    VISITOR_GUARD,
    VISITOR_LOOP,
    VISITOR_MISSING,
)
from app.spec_parser.symbol_index import SymbolIndex
from app.spec_parser.visitors.guard_raise import function_has_guard_raise
from app.spec_parser.visitors.return_shape import (
    ForLoopVisitor,
    ReturnShapeVisitor,
    index_class_methods,
)
from app.task import Task


def run_generic_enrichment(
    task: Task,
    scope: AnalysisScope,
    draft: StructuredSpecification,
    index: SymbolIndex,
) -> RepoEnrichment:
    root = Path(task.project_path)
    missing_handlers: set[str] = set(scope.missing_symbols)
    co_fix: set[str] = set()
    neighbor: str | None = None
    arch_pattern = "unknown"
    negative: set[str] = set()
    snippets: dict[str, str] = {}
    hints: set[str] = set()
    target_files: list[str] = []

    required_methods: set[str] = set()
    for m in scope.methods:
        required_methods.add(m.split(".")[-1])
    for sym in scope.missing_symbols:
        required_methods.add(sym.split(".")[-1])

    for rel in scope.files:
        fpath = root / rel
        if not fpath.is_file():
            continue
        target_files.append(rel)
        try:
            source = fpath.read_text(errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, OSError):
            continue

        methods_map = index_class_methods(source)
        hints.update(methods_map.keys())

        if VISITOR_MISSING in scope.visitors:
            for req in required_methods:
                if req not in methods_map:
                    missing_handlers.add(req)

        class_filter = set(scope.classes) if scope.classes else None

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            mname = node.name
            if class_filter:
                parent_class = _parent_class(tree, node)
                if parent_class and parent_class not in class_filter:
                    if mname not in required_methods:
                        continue

            if VISITOR_GUARD in scope.visitors:
                has_guard, msgs = function_has_guard_raise(source, mname)
                if has_guard:
                    arch_pattern = "guard"
                    snippets[f"guard:{mname}"] = "\n".join(source.splitlines()[
                        max(0, node.lineno - 1) : node.lineno + 3
                    ])
                    if msgs:
                        snippets[f"guard_msg:{mname}"] = msgs[0]

            if VISITOR_DELEGATE in scope.visitors and mname.startswith("_"):
                vis = ReturnShapeVisitor()
                for child in ast.walk(node):
                    if isinstance(child, ast.Return):
                        vis.visit_Return(child)
                if vis.features.has_self_print_return and vis.features.has_ast_compose:
                    neighbor = mname
                    arch_pattern = "delegate"
                if vis.features.has_inline_ternary:
                    negative.add("inline_ternary_pattern")

            if VISITOR_LOOP in scope.visitors:
                vis = ForLoopVisitor()
                vis.visit(node)
                for loop in vis.loops:
                    if loop.is_unclamped_j_loop and loop.accesses_self_ij:
                        co_fix.add(mname)
                        arch_pattern = "loop_clamp"
                        if scope.expand_siblings:
                            co_fix.update(
                                n
                                for n in methods_map
                                if n != mname and not n.startswith("__")
                            )

    if draft.fix_scope.co_fix_required:
        co_fix.update(draft.fix_scope.co_fix_required)

    confidence = 0.5
    if target_files:
        confidence += 0.2
    if missing_handlers or co_fix or neighbor:
        confidence += 0.15
    if arch_pattern != "unknown":
        confidence += 0.1
    confidence = min(1.0, confidence)

    return RepoEnrichment(
        target_files=target_files,
        missing_handlers=sorted(missing_handlers),
        co_fix_candidates=sorted(co_fix),
        neighbor_reference=neighbor,
        architecture_pattern=arch_pattern,
        negative_patterns=sorted(negative),
        search_api_hints=sorted(hints)[:20],
        evidence_snippets=snippets,
        context_domain=scope.context_domain,
        enrichment_confidence=confidence,
    )


def _parent_class(tree: ast.Module, func_node: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if item is func_node:
                    return node.name
    return None
