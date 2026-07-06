"""
Contract feature extraction for L2 evidence triangulation (HC v1).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# Thresholds — centralized for lite300 calibration
CALLEE_JACCARD_CONFLICT_LOW = 0.3
CALLEE_JACCARD_ALIGN_HIGH = 0.6
FEATURE_COVERAGE_MIN = 0.5

_PRINT_CALLEES = frozenset({"_print", "doprint", "stringify", "printer"})
_COMPOSE_TYPES = frozenset(
    {"Piecewise", "Relational", "And", "Or", "Not", "Eq", "Ne", "Lt", "Le", "Gt", "Ge"}
)


@dataclass(frozen=True)
class ContractFeatureSet:
    callees: frozenset[str]
    string_literal_prefixes: frozenset[str]
    has_self_print: bool
    has_ast_compose: bool
    return_expr_unparsed: str | None


class ReturnFeatureVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.callees: set[str] = set()
        self.string_literal_prefixes: set[str] = set()
        self.has_self_print = False
        self.has_ast_compose = False
        self.return_expr_unparsed: str | None = None

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self._visit_expr(node.value)
            try:
                self.return_expr_unparsed = ast.unparse(node.value)[:500]
            except Exception:
                self.return_expr_unparsed = None

    def _visit_expr(self, node: ast.AST) -> None:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute):
                    name = func.attr
                    self.callees.add(name)
                    if name == "_print" and isinstance(func.value, ast.Name):
                        if func.value.id == "self":
                            self.has_self_print = True
                elif isinstance(func, ast.Name):
                    self.callees.add(func.id)
                    if func.id in _COMPOSE_TYPES:
                        self.has_ast_compose = True
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                val = child.value
                if val:
                    self.string_literal_prefixes.add(val[:20])
            elif isinstance(child, ast.JoinedStr):
                self.string_literal_prefixes.add("f-string")


def extract_from_source(source: str, method_name: str | None = None) -> ContractFeatureSet | None:
    """Extract contract features from Python source (full file or snippet)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    visitor = ReturnFeatureVisitor()
    if method_name:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == method_name:
                    for child in ast.walk(node):
                        if isinstance(child, ast.Return):
                            visitor.visit_Return(child)
                    break
    else:
        visitor.visit(tree)

    return ContractFeatureSet(
        callees=frozenset(visitor.callees),
        string_literal_prefixes=frozenset(visitor.string_literal_prefixes),
        has_self_print=visitor.has_self_print,
        has_ast_compose=visitor.has_ast_compose,
        return_expr_unparsed=visitor.return_expr_unparsed,
    )


def extract_from_issue(issue_text: str) -> ContractFeatureSet | None:
    """Extract features from fenced code blocks in issue text."""
    blocks = re.findall(r"```(?:python)?\s*\n(.*?)```", issue_text, re.DOTALL | re.IGNORECASE)
    if not blocks:
        return None
    combined = "\n".join(blocks)
    return extract_from_source(combined)


def extract_from_intended_behavior(text: str) -> ContractFeatureSet:
    """Weak text-side feature extraction from intended_behavior."""
    callees: set[str] = set()
    for c in _PRINT_CALLEES:
        if c in text:
            callees.add(c)
    if "self._print" in text or "_print(" in text:
        callees.add("_print")
    prefixes: set[str] = set()
    for m in re.finditer(r'["\']([^"\']{1,30})', text):
        prefixes.add(m.group(1)[:20])
    return ContractFeatureSet(
        callees=frozenset(callees),
        string_literal_prefixes=frozenset(prefixes),
        has_self_print="self._print" in text or "_print(" in text,
        has_ast_compose=any(t in text for t in _COMPOSE_TYPES),
        return_expr_unparsed=None,
    )


def callee_jaccard(a: ContractFeatureSet, b: ContractFeatureSet) -> float:
    ua = a.callees | a.string_literal_prefixes
    ub = b.callees | b.string_literal_prefixes
    if not ua and not ub:
        return 1.0
    if not ua or not ub:
        return 0.0
    return len(ua & ub) / len(ua | ub)


def feature_coverage(ib_fs: ContractFeatureSet, neighbor_fs: ContractFeatureSet) -> float:
    if not neighbor_fs.callees:
        return 1.0
    return len(ib_fs.callees & neighbor_fs.callees) / len(neighbor_fs.callees)


def contracts_conflict(
    issue_fs: ContractFeatureSet | None,
    neighbor_fs: ContractFeatureSet | None,
    ib_fs: ContractFeatureSet | None,
) -> bool:
    if issue_fs is None or neighbor_fs is None or ib_fs is None:
        return False
    if callee_jaccard(issue_fs, neighbor_fs) < CALLEE_JACCARD_CONFLICT_LOW:
        if callee_jaccard(ib_fs, issue_fs) > CALLEE_JACCARD_ALIGN_HIGH:
            if callee_jaccard(ib_fs, neighbor_fs) < CALLEE_JACCARD_CONFLICT_LOW:
                return True
    return False
