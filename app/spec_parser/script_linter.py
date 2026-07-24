"""Static preflight checks for generated acceptance scripts."""

from __future__ import annotations

import ast
import re

from app import config
from app.spec_parser.ac_markers import parse_ac_sections
from app.spec_parser.grounding import enforceable_co_fix, enforceable_prerequisite
from app.spec_parser.schema import ScriptLintReport, StructuredSpecification, TaskType

_STUB_RE = re.compile(r'AssertionError\s*\(\s*[\'"]Stub\b', re.IGNORECASE)
_TEST_DEF_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.MULTILINE)
_PROJECT_CALL_RE = re.compile(
    r"\b(assert|getattr|setattr|open|requests\.|httpx\.|client\.|"
    r"CliRunner|TestClient|subprocess\.|Retort|Monitor|load|dump|parse|format_|"
    r"invoke|click\.|main\(|\.run\(|\.call\(|\.execute\()\b",
    re.IGNORECASE,
)
_EMPTY_FAIL_RAISE_RE = re.compile(
    r"raise\s+(NotImplementedError|"
    r"AssertionError\s*\([^)]*NOT_IMPLEMENTED)",
    re.IGNORECASE,
)


def _must_ids(spec: StructuredSpecification) -> list[str]:
    return [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]


def _section_text(script: str, ac_id: str, section_map) -> str:
    from app.spec_parser.ac_markers import extract_ac_section_body

    body = extract_ac_section_body(script, ac_id)
    return body or ""


def preflight(
    spec: StructuredSpecification,
    script: str,
    *,
    issue_text: str = "",
) -> ScriptLintReport:
    """Run static lint rules before sandbox execution."""
    must = _must_ids(spec)
    section_map = parse_ac_sections(script, must)
    blocking: list[str] = []
    warnings: list[str] = []

    if section_map.missing:
        blocking.append("L1-MISSING-AC")

    for entity in enforceable_co_fix(spec, issue_text):
        if entity.lower() not in script.lower():
            blocking.append("L2-COFIX-COVERAGE")
        elif _co_fix_lacks_executable_assert(script, entity, section_map):
            blocking.append("L2-COFIX-WEAK")

    # v3.4: L10 blocking only when ALL found Must ACs are existence-only;
    # partial existence → L10w warning (legacy soft).
    exist_stats = _existence_ac_stats(script, section_map)
    if exist_stats["n_found"] > 0 and exist_stats["n_existence"] >= exist_stats["n_found"]:
        blocking.append("L10-EXISTENCE-ONLY")
    elif exist_stats["n_existence"] > 0:
        warnings.append("L10w-PARTIAL-EXISTENCE")

    if _has_vacuous_assert(script, section_map):
        blocking.append("L13-VACUOUS-ASSERT")

    if _has_dead_test_functions(script):
        blocking.append("L11-DEAD-AC")

    if _has_stub_only_ac(script, section_map):
        blocking.append("L12-STUB-AC")

    if _has_empty_fail_ac(script, section_map):
        blocking.append("L14-EMPTY-FAIL")

    if getattr(config, "spec_parser_enable_failure_semantics_check", True):
        from app.spec_parser.failure_semantics import check_failure_semantics

        eg = check_failure_semantics(script)
        for rule in eg.blocking:
            if rule not in blocking:
                blocking.append(rule)

    if _has_weak_sinc_only(script, spec):
        blocking.append("L3-WEAK-ASSERT-SINC")

    if _missing_prerequisite_probe(script, spec, issue_text=issue_text):
        blocking.append("L3-WEAK-ASSERT-PREREQ")

    if _uses_numpy_lambdify(script):
        blocking.append("L7-NUMPY-LAMBDA")

    if _bad_future_import(script):
        blocking.append("L8-FUTURE-IMPORT")

    if _fake_import_modules(script):
        blocking.append("L9-FAKE-IMPORT")

    if _has_swallowed_exceptions(script, section_map):
        blocking.append("L4-SWALLOW-EXCEPTION")

    if spec.task_type == TaskType.BUG_FIX and not _has_hard_fail_path(script):
        warnings.append("L5-EXIT-PATH")

    if section_map.unknown:
        warnings.append("L6-UNKNOWN-AC")

    return ScriptLintReport(
        passed=not blocking,
        blocking_rules=blocking,
        warnings=warnings,
        ac_section_map={k: v for k, v in section_map.found.items()},
        missing_ac_ids=list(section_map.missing),
    )


def lint_feedback(report: ScriptLintReport) -> str:
    parts = [f"preflight failed: {', '.join(report.blocking_rules)}"]
    if report.missing_ac_ids:
        parts.append(f"missing AC ids: {report.missing_ac_ids}")
    return "; ".join(parts)


def _co_fix_lacks_executable_assert(script: str, entity: str, section_map) -> bool:
    """co_fix name appears but no AC section containing it has assert/raise."""
    el = entity.lower()
    if el not in script.lower():
        return False
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if el not in body.lower():
            continue
        if re.search(r"\bassert\b|\braise\b", body):
            return False
    return True


def _is_existence_only_assert(stmt: str) -> bool:
    s = stmt.strip()
    if re.fullmatch(r"assert\s+True\b.*", s, re.DOTALL):
        return True
    if re.fullmatch(r"assert\s+hasattr\s*\([^)]+\)\s*(,\s*.*)?", s, re.DOTALL):
        return True
    if re.fullmatch(r"assert\s+callable\s*\([^)]+\)\s*(,\s*.*)?", s, re.DOTALL):
        return True
    if re.fullmatch(
        r"assert\s+\w+(\.\w+)*\s+is\s+not\s+None\s*(,\s*.*)?", s, re.DOTALL
    ):
        return True
    return False


def _behavioral_assert_lines(body: str) -> list[str]:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("assert "):
            lines.append(stripped)
    return lines


def _existence_ac_stats(script: str, section_map) -> dict[str, int]:
    """Count found AC sections vs existence-only sections (v3.4 L10/L10w)."""
    n_found = 0
    n_existence = 0
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if not body or not body.strip():
            continue
        n_found += 1
        asserts = _behavioral_assert_lines(body)
        has_existence_call = bool(re.search(r"\bhasattr\s*\(|\bcallable\s*\(|\bin\s+dir\s*\(", body))
        is_exist = False
        if asserts and all(_is_existence_only_assert(a) for a in asserts):
            is_exist = True
        elif has_existence_call and not asserts:
            is_exist = True
        elif has_existence_call and asserts and all(
            _is_existence_only_assert(a) for a in asserts
        ):
            is_exist = True
        if is_exist:
            n_existence += 1
    return {"n_found": n_found, "n_existence": n_existence}


def _has_existence_only_ac(script: str, section_map) -> bool:
    """True if some AC section only has existence-style asserts (no real behavior)."""
    stats = _existence_ac_stats(script, section_map)
    return stats["n_existence"] > 0


def _has_vacuous_assert(script: str, section_map) -> bool:
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if re.search(r"\bassert\s+True\b", body):
            return True
    # also catch module-level outside sections
    if section_map.found and re.search(r"\bassert\s+True\b", script):
        # already covered per-section; keep consistent
        pass
    return False


def _has_dead_test_functions(script: str) -> bool:
    """Nested/top-level test_* defs that are never called → dead AC pattern."""
    defined = set(_TEST_DEF_RE.findall(script))
    if not defined:
        return False
    called: set[str] = set()
    try:
        tree = ast.parse(script)
    except SyntaxError:
        # fallback: any call-looking use outside def lines
        for name in defined:
            if re.search(rf"(?<!def )\b{re.escape(name)}\s*\(", script):
                called.add(name)
        return bool(defined - called)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in defined:
                called.add(func.id)
            elif isinstance(func, ast.Attribute) and func.attr in defined:
                called.add(func.attr)
    return bool(defined - called)


def _has_stub_only_ac(script: str, section_map) -> bool:
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if not body.strip():
            continue
        # Strip comments/blank lines
        code_lines = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not code_lines:
            continue
        joined = "\n".join(code_lines)
        if _STUB_RE.search(joined) and not re.search(
            r"\bassert\b", joined
        ):
            # Only raise Stub... (optionally try/except wrappers)
            if "raise AssertionError" in joined or _STUB_RE.search(joined):
                # If body has no project-facing call besides raise, treat as stub
                if not _PROJECT_CALL_RE.search(joined):
                    return True
                # Explicit Stub message with only raise lines
                non_raise = [
                    ln
                    for ln in code_lines
                    if not ln.startswith(("raise ", "try:", "except", "pass"))
                    and "AssertionError" not in ln
                ]
                if not non_raise and _STUB_RE.search(joined):
                    return True
    return False


def _ac_has_product_probe(joined: str) -> bool:
    """True when AC body probes a product API (call/attr) beyond empty-fail raises."""
    if re.search(
        r"\b(getattr|setattr|open|requests\.|httpx\.|client\.|"
        r"CliRunner|TestClient|subprocess\.|Retort|Monitor|load|dump|parse|"
        r"format_|invoke|click\.|main\()\b",
        joined,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"\.\s*(run|call|execute|invoke|get|post|put|delete)\s*\(", joined):
        return True
    # Any non-trivial call that is not hasattr/callable/print/len/str/...
    for m in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", joined):
        name = m.group(1)
        if name in {
            "hasattr",
            "callable",
            "isinstance",
            "len",
            "str",
            "int",
            "print",
            "AssertionError",
            "NotImplementedError",
            "Exception",
            "AttributeError",
            "ImportError",
            "ModuleNotFoundError",
            "ValueError",
            "TypeError",
            "KeyError",
            "RuntimeError",
            "range",
            "list",
            "dict",
            "set",
            "tuple",
        }:
            continue
        return True
    return False


def _has_empty_fail_ac(script: str, section_map) -> bool:
    """L14: AC body is only NotImplementedError / NOT_IMPLEMENTED with no product probe."""
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if not body.strip():
            continue
        code_lines = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not code_lines:
            continue
        joined = "\n".join(code_lines)
        if not _EMPTY_FAIL_RAISE_RE.search(joined):
            continue
        if _ac_has_product_probe(joined):
            continue
        return True
    return False


def count_behavioral_acs(script: str, must_ids: list[str] | None = None) -> dict[str, int]:
    """Count AC sections by behavioral / existence / empty-fail (for draft_picker)."""
    from app.spec_parser.ac_markers import parse_ac_sections

    ids = must_ids or []
    section_map = parse_ac_sections(script, ids)
    behavioral = 0
    existence = 0
    empty_fail = 0
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        code_lines = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        joined = "\n".join(code_lines)
        if not joined:
            continue
        if _EMPTY_FAIL_RAISE_RE.search(joined) and not _ac_has_product_probe(joined):
            empty_fail += 1
            continue
        if _is_existence_only_body(joined):
            existence += 1
            continue
        if _ac_has_product_probe(joined) or re.search(r"\bassert\b", joined):
            behavioral += 1
    return {
        "behavioral_ac_count": behavioral,
        "existence_only_ac_count": existence,
        "empty_fail_ac_count": empty_fail,
    }


def _is_existence_only_body(joined: str) -> bool:
    """Heuristic: body only checks hasattr/callable/is not None."""
    if not joined.strip():
        return False
    if _ac_has_product_probe(joined):
        return False
    existence_hits = len(
        re.findall(
            r"\bhasattr\s*\(|\bcallable\s*\(|\bis\s+not\s+None\b|\bassert\s+True\b",
            joined,
        )
    )
    assert_hits = len(re.findall(r"\bassert\b", joined))
    return existence_hits > 0 and assert_hits > 0 and existence_hits >= assert_hits


def _has_weak_sinc_only(script: str, spec: StructuredSpecification) -> bool:
    blob = " ".join(spec.repair_goals + spec.symptom_goals).lower()
    needs_sinc = "sinc" in blob or any(
        "sinc" in ac.covers_entity.lower() or "sinc" in ac.observable.lower()
        for ac in spec.acceptance_criteria
    )
    if not needs_sinc:
        return False
    has_rel = any(
        p.lower() in script.lower()
        for p in spec.fix_scope.prerequisite
        if "relational" in p.lower() or "ne(" in p.lower()
    )
    if has_rel:
        return False
    weak = re.search(
        r'assert\s+["\']Not supported["\']\s+not\s+in',
        script,
        re.IGNORECASE,
    )
    strong = "Ne(" in script or "Piecewise" in script or "\\n" in script
    return bool(weak and not strong)


def _missing_prerequisite_probe(
    script: str,
    spec: StructuredSpecification,
    *,
    issue_text: str = "",
) -> bool:
    for prereq in enforceable_prerequisite(spec, issue_text):
        pl = prereq.lower()
        if "relational" in pl or "_print_relational" in pl:
            if not any(
                tok in script
                for tok in ("Ne(", "Eq(", "_print_Relational", "Relational")
            ):
                return True
    return False


def _uses_numpy_lambdify(script: str) -> bool:
    if "lambdify" in script and re.search(r"['\"]numpy['\"]", script):
        return True
    if re.search(r"import\s+numpy\b", script):
        return True
    return False


def _bad_future_import(script: str) -> bool:
    if "from __future__" not in script:
        return False
    code_lines = [
        line.strip()
        for line in script.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for i, stripped in enumerate(code_lines):
        if stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        if stripped.startswith("from __future__"):
            return i > 0
    return False


def _fake_import_modules(script: str) -> bool:
    fake = ("get_sympy", "path_hack", "sympy_path_hack")
    return any(f"import {m}" in script or f"from {m}" in script for m in fake)


def _except_type_is_broad(node: ast.ExceptHandler) -> bool:
    t = node.type
    if t is None:
        return True
    if isinstance(t, ast.Name) and t.id in ("Exception", "BaseException"):
        return True
    if isinstance(t, ast.Tuple):
        return any(
            isinstance(e, ast.Name) and e.id in ("Exception", "BaseException")
            for e in t.elts
        )
    return False


def _handler_rethrows_assertion_or_any(node: ast.ExceptHandler, body_src: str) -> bool:
    handler_src = ast.get_source_segment(body_src, node) or ""
    if re.search(r"raise\s+AssertionError", handler_src):
        return True
    return any(isinstance(s, ast.Raise) for s in node.body)


def _has_swallowed_exceptions(script: str, section_map) -> bool:
    """v3.2: block swallows; allow expected-product-exception + pass, or re-raise AC FAIL."""
    for ac_id in section_map.found:
        from app.spec_parser.ac_markers import extract_ac_section_body

        body = extract_ac_section_body(script, ac_id) or ""
        if "except " not in body and "except:" not in body:
            continue
        try:
            tree = ast.parse(body)
        except SyntaxError:
            # Fallback regex for unparseable fragments: bare except: pass
            if re.search(
                r"except\s*(?:Exception|BaseException)?\s*:\s*\n(?:[ \t]*\n)*[ \t]+pass\b",
                body,
            ):
                return True
            if re.search(
                r"except(?:\s+[^:]*)?:\s*\n(?:[ \t]*\n)*[ \t]+return\s+False\b",
                body,
            ):
                return True
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            stmts = node.body
            if not stmts:
                return True
            if (
                len(stmts) == 1
                and isinstance(stmts[0], ast.Return)
                and isinstance(stmts[0].value, ast.Constant)
                and stmts[0].value.value is False
            ):
                return True
            only_pass = len(stmts) == 1 and isinstance(stmts[0], ast.Pass)
            if only_pass:
                # Legal: except SpecificError: pass (negative AC expecting that error)
                # Illegal: except: / except Exception: / except BaseException: pass
                if _except_type_is_broad(node):
                    return True
                continue
            if not _handler_rethrows_assertion_or_any(node, body):
                if _except_type_is_broad(node):
                    return True
    return False


def _has_hard_fail_path(script: str) -> bool:
    return (
        "sys.exit(1)" in script
        or "raise AssertionError" in script
        or re.search(r"AC-[A-Z0-9]+\s+FAIL", script, re.IGNORECASE) is not None
    )


def should_run_preflight() -> bool:
    return getattr(config, "spec_parser_script_preflight", True)
