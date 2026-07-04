"""Detect guard-style raise patterns in functions."""

from __future__ import annotations

import ast


class GuardRaiseVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.has_guard_raise = False
        self.raise_messages: list[str] = []

    def visit_Raise(self, node: ast.Raise) -> None:
        msg = ""
        if node.exc is not None:
            try:
                msg = ast.unparse(node.exc)
            except Exception:
                msg = ""
        self.raise_messages.append(msg[:200])
        for parent in _walk_parents(node):
            if isinstance(parent, ast.If):
                self.has_guard_raise = True
                break


def _walk_parents(node: ast.AST) -> list[ast.AST]:
    # Without parent links, approximate: treat Raise inside If via visit
    return []


def function_has_guard_raise(source: str, method_name: str) -> tuple[bool, list[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False, []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name != method_name and not method_name.endswith(f".{node.name}"):
                if method_name != node.name:
                    continue
            vis = _GuardRaiseInFunctionVisitor()
            vis.visit(node)
            if vis.has_guard_raise:
                return True, vis.raise_messages
    return False, []


class _GuardRaiseInFunctionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.has_guard_raise = False
        self.raise_messages: list[str] = []

    def visit_If(self, node: ast.If) -> None:
        for child in ast.walk(node):
            if child is not node and isinstance(child, ast.If):
                continue
            if isinstance(child, ast.Raise):
                self.has_guard_raise = True
                if child.exc is not None:
                    try:
                        self.raise_messages.append(ast.unparse(child.exc)[:200])
                    except Exception:
                        pass
        self.generic_visit(node)
