"""Find sibling methods sharing the same AST anti-pattern (repo-agnostic)."""

from __future__ import annotations

import ast

from app.spec_parser.visitors.return_shape import ForLoopVisitor


def find_unclamped_j_loop_methods(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            vis = ForLoopVisitor()
            vis.visit(node)
            if any(l.is_unclamped_j_loop and l.accesses_self_ij for l in vis.loops):
                found.add(node.name)
    return found


def expand_loop_siblings(source: str, trigger_method: str) -> set[str]:
    """Methods in the same file that share the unclamped-j-loop anti-pattern."""
    all_unclamped = find_unclamped_j_loop_methods(source)
    if trigger_method in all_unclamped:
        return all_unclamped
    return {trigger_method} if trigger_method else set()
