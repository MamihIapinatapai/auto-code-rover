"""AST visitors for repo enrichment."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class ReturnShapeFeatures:
    has_string_return: bool = False
    has_self_print_return: bool = False
    has_inline_ternary: bool = False
    has_ast_compose: bool = False


class ReturnShapeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.features = ReturnShapeFeatures()

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is None:
            return
        src = ""
        try:
            src = ast.unparse(node.value)
        except Exception:
            pass
        if "?" in src and ":" in src:
            self.features.has_inline_ternary = True
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            self.features.has_string_return = True
        for child in ast.walk(node.value):
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                if child.func.attr == "_print" and isinstance(child.func.value, ast.Name):
                    if child.func.value.id == "self":
                        self.features.has_self_print_return = True
            if isinstance(child, ast.Name) and child.id in {
                "Piecewise",
                "Ne",
                "Eq",
                "Relational",
            }:
                self.features.has_ast_compose = True


@dataclass
class ForLoopFeatures:
    loop_var: str = ""
    range_expr: str = ""
    accesses_self_ij: bool = False
    is_unclamped_j_loop: bool = False


class ForLoopVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.loops: list[ForLoopFeatures] = []

    def visit_For(self, node: ast.For) -> None:
        feat = ForLoopFeatures()
        if isinstance(node.target, ast.Name):
            feat.loop_var = node.target.id
        try:
            feat.range_expr = ast.unparse(node.iter)
        except Exception:
            feat.range_expr = ""
        body_src = ""
        try:
            body_src = ast.unparse(node)
        except Exception:
            pass
        feat.accesses_self_ij = "self[" in body_src or "self (" in body_src
        if feat.loop_var == "j" and "range(i)" in feat.range_expr.replace(" ", ""):
            if "min(" not in body_src and "self.cols" not in feat.range_expr:
                feat.is_unclamped_j_loop = True
        self.loops.append(feat)
        self.generic_visit(node)


def index_class_methods(source: str, class_name: str | None = None) -> dict[str, int]:
    """Return method_name -> lineno for methods in a class."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    methods: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if class_name and node.name != class_name:
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = item.lineno
    return methods
