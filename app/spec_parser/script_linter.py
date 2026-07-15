"""Static preflight checks for generated acceptance scripts."""

from __future__ import annotations

import re

from app import config
from app.spec_parser.ac_markers import parse_ac_sections
from app.spec_parser.grounding import enforceable_co_fix, enforceable_prerequisite
from app.spec_parser.schema import ScriptLintReport, StructuredSpecification, TaskType


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

    if getattr(config, "spec_parser_use_v3_prompts", False) and _has_existence_only_ac(
        script, section_map
    ):
        blocking.append("L10-EXISTENCE-ONLY")

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


def _has_existence_only_ac(script: str, section_map) -> bool:
    for ac_id in section_map.found:
        body = _section_text(script, ac_id, section_map)
        if not body:
            continue
        has_existence = bool(re.search(r"\bhasattr\s*\(|\bcallable\s*\(", body))
        has_behavior = bool(
            re.search(r"\bassert\b", body)
            and not re.fullmatch(
                r"\s*assert\s+hasattr\s*\([^)]+\)\s*",
                body.strip(),
                re.DOTALL,
            )
        )
        if has_existence and not has_behavior:
            return True
    return False


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


def _has_swallowed_exceptions(script: str, section_map) -> bool:
    for ac_id in section_map.found:
        from app.spec_parser.ac_markers import extract_ac_section_body

        body = extract_ac_section_body(script, ac_id) or ""
        if "except " in body and "raise AssertionError" not in body:
            if re.search(r"return\s+False", body):
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
