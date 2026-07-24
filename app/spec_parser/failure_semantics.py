"""v3.5 failure semantics / Executableity Gate (δ)."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from app.spec_parser.recipe_loader import recipe_compliance

_STUB_INVOKE_RE = re.compile(r"None\s*#\s*invoke", re.I)
_AWAIT_NONE_RE = re.compile(r"await\s+None\b")
_NOT_IMPL_MSG_RE = re.compile(r"NOT_IMPLEMENTED", re.I)
_AC_SPLIT_RE = re.compile(r"(?=#\s*---\s*AC-)", re.I)

_NON_PRODUCT_CALLS = frozenset(
    {
        "print",
        "len",
        "list",
        "dict",
        "set",
        "tuple",
        "str",
        "int",
        "bool",
        "type",
        "isinstance",
        "issubclass",
        "getattr",
        "setattr",
        "hasattr",
        "callable",
        "open",
        "repr",
        "sorted",
        "enumerate",
        "range",
        "iter",
        "next",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "MagicMock",
        "Mock",
        "AsyncMock",
        "patch",
    }
)


@dataclass
class FailureSemanticsReport:
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    per_ac: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.blocking


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _full_attr(node: ast.AST) -> str:
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add((alias.asname or alias.name).split(".")[0])
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
            for alias in node.names:
                roots.add(alias.asname or alias.name)
    return roots


def _is_product_call(
    call: ast.Call,
    *,
    import_roots: set[str],
    sut_packages: set[str] | None,
    product_names: set[str],
) -> bool:
    name = _call_name(call.func)
    full = _full_attr(call.func)
    base = full.split(".")[0] if full else name
    if name in _NON_PRODUCT_CALLS or base in _NON_PRODUCT_CALLS:
        return False
    if full.startswith("pytest.") or full.startswith("unittest."):
        return False
    if product_names and (
        name in product_names
        or full in product_names
        or any(p and p in full for p in product_names)
    ):
        return True
    if sut_packages and base in sut_packages:
        return True
    if base in import_roots and base not in {
        "pytest",
        "unittest",
        "sys",
        "os",
        "re",
        "json",
        "asyncio",
        "typing",
    }:
        return True
    return False


def _section_chunks(script: str) -> list[tuple[str, str]]:
    parts = [p for p in _AC_SPLIT_RE.split(script) if p and p.strip()]
    out: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        m = re.search(r"AC-([A-Za-z0-9_]+)", part)
        mid = m.group(1) if m else f"S{i}"
        out.append((mid, part))
    if not out:
        out.append(("M1", script))
    return out


def check_failure_semantics(
    script: str,
    *,
    recipe_id: str | None = None,
    recipe_cards: dict | None = None,
    sut_packages: list[str] | set[str] | None = None,
    product_names: list[str] | set[str] | None = None,
) -> FailureSemanticsReport:
    report = FailureSemanticsReport()
    text = script or ""
    sut = set(sut_packages or [])
    products = set(product_names or [])

    if _STUB_INVOKE_RE.search(text) or _AWAIT_NONE_RE.search(text):
        report.blocking.append("EG-01")

    try:
        tree = ast.parse(text)
    except SyntaxError:
        report.blocking.append("EG-SYNTAX")
        return report

    import_roots = _import_roots(tree)
    chunks = _section_chunks(text)
    any_product = False

    for ac_id, section in chunks:
        # Preamble-only chunks (imports / module docstring before first AC-*)
        # must not trigger EG-02 — only executable AC bodies are gated.
        if not re.search(r"\bdef\s+test_", section) and len(chunks) > 1:
            continue
        try:
            sec_tree = ast.parse(section)
        except SyntaxError:
            sec_tree = tree
        calls = [n for n in ast.walk(sec_tree) if isinstance(n, ast.Call)]
        product_calls = [
            c
            for c in calls
            if _is_product_call(
                c,
                import_roots=import_roots,
                sut_packages=sut,
                product_names=products,
            )
        ]
        has_product = bool(product_calls)
        if has_product:
            any_product = True
        report.per_ac[str(ac_id)] = {
            "product_call_count": len(product_calls),
            "call_count": len(calls),
        }
        if not has_product:
            report.blocking.append("EG-02")

        for node in ast.walk(sec_tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    ctx = item.context_expr
                    if not isinstance(ctx, ast.Call):
                        continue
                    fname = _full_attr(ctx.func)
                    if fname.split(".")[-1] != "raises":
                        continue
                    body_product = any(
                        _is_product_call(
                            c,
                            import_roots=import_roots,
                            sut_packages=sut,
                            product_names=products,
                        )
                        for stmt in node.body
                        for c in ast.walk(stmt)
                        if isinstance(c, ast.Call)
                    )
                    if not body_product:
                        report.blocking.append("EG-03")

            if isinstance(node, ast.Raise) and node.exc is not None:
                exc = node.exc
                msg = ""
                if isinstance(exc, ast.Call) and _call_name(exc.func) in {
                    "AssertionError",
                    "NotImplementedError",
                }:
                    if exc.args and isinstance(exc.args[0], ast.Constant):
                        msg = str(exc.args[0].value)
                if _NOT_IMPL_MSG_RE.search(msg) and not has_product:
                    report.blocking.append("EG-04")

    if not any_product and "EG-02" not in report.blocking:
        report.blocking.append("EG-02")

    if recipe_id and recipe_cards:
        card = recipe_cards.get(recipe_id) or {}
        if card.get("blocking") and not recipe_compliance(text, recipe_id):
            report.blocking.append("EG-05")

    seen: set[str] = set()
    uniq: list[str] = []
    for b in report.blocking:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    report.blocking = uniq
    return report


def classify_failure_provenance(
    *,
    script: str = "",
    evidence: dict[str, Any] | None = None,
    static_report: FailureSemanticsReport | None = None,
) -> dict[str, Any]:
    evidence = evidence or {}
    static_report = static_report or check_failure_semantics(script)
    if not evidence:
        return {
            "failure_provenance": "missing",
            "synthetic_fail": False,
            "stub_unexpected_pass": bool(static_report.blocking),
            "weak_green": False,
            "per_ac_provenance": {},
        }

    overall_pass = bool(evidence.get("overall_pass") or evidence.get("passed"))
    unexpected_pass = bool(evidence.get("unexpected_pass"))
    stderr = str(evidence.get("stderr") or evidence.get("stderr_excerpt") or "")
    triage = str(evidence.get("triage") or "")

    if triage in {"harness_error", "missing_third_party", "missing_feature_module"}:
        prov = "env"
    elif static_report.blocking and (overall_pass or unexpected_pass):
        prov = "stub_pass"
    elif _NOT_IMPL_MSG_RE.search(stderr) and "test_" in stderr:
        prov = "synthetic"
    elif overall_pass or unexpected_pass:
        prov = "unknown"
    else:
        prov = "product"

    weak = (overall_pass or unexpected_pass) and not static_report.blocking and prov not in {
        "stub_pass",
        "synthetic",
    }
    return {
        "failure_provenance": prov,
        "synthetic_fail": prov == "synthetic",
        "stub_unexpected_pass": prov == "stub_pass",
        "weak_green": weak,
        "per_ac_provenance": evidence.get("per_ac_provenance") or {},
    }
