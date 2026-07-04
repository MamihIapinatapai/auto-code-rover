"""Deterministic contract → AnalysisScope compilation."""

from __future__ import annotations

from app import config
from app.spec_parser.schema import AnalysisScope, StructuredSpecification
from app.spec_parser.symbol_index import SymbolIndex
from app.spec_parser.target_resolution import FileCandidate

LOOP_KEYWORDS = (
    "indexerror",
    "index error",
    "out of range",
    "range(",
    "range (",
    "bounds",
    "hessenberg",
    "dimension",
    "clamp",
)

VISITOR_GUARD = "guard_raise"
VISITOR_DELEGATE = "delegate_call"
VISITOR_LOOP = "loop_bound"
VISITOR_MISSING = "missing_symbol"


def _goal_text(draft: StructuredSpecification) -> str:
    parts = list(draft.symptom_goals) + list(draft.repair_goals)
    return " ".join(parts).lower()


def _must_symbols(draft: StructuredSpecification) -> set[str]:
    symbols: set[str] = set()
    if draft.failure_anchor:
        symbols.update(draft.failure_anchor.named_entities)
    for ac in draft.acceptance_criteria:
        if ac.covers_entity:
            symbols.add(ac.covers_entity)
    for label in (
        draft.fix_scope.in_scope
        + draft.fix_scope.co_fix_required
        + draft.fix_scope.prerequisite
    ):
        symbols.add(label)
    return {s for s in symbols if s.strip()}


def compile_analysis_scope(
    draft: StructuredSpecification,
    candidates: list[FileCandidate],
    index: SymbolIndex,
    context_domain: str,
) -> AnalysisScope:
    files = [c.rel_path for c in candidates]
    classes: set[str] = set()
    methods: set[str] = set()
    missing: set[str] = set()

    for sym in _must_symbols(draft):
        short = sym.split(".")[-1] if "." in sym else sym
        if sym.endswith(" constructor"):
            cls = sym[: -len(" constructor")].strip()
            classes.add(cls)
            methods.add(f"{cls}.__init__")
            continue
        if index.classes.get(sym) or index.classes.get(short):
            classes.add(sym.split(".")[0] if "." in sym else sym)
        if index.functions.get(sym) or index.functions.get(short):
            methods.add(sym if "." in sym else short)
        elif short.startswith("_") or short.isidentifier():
            found = bool(index.functions.get(short))
            if not found and sym not in missing:
                missing.add(sym)

    visitors: list[str] = [VISITOR_MISSING]
    layer = draft.architecture_hint.layer
    pattern = draft.architecture_hint.pattern
    text = _goal_text(draft)

    if layer == "guard" or layer == "bracket_decision":
        visitors.append(VISITOR_GUARD)
    if layer == "delegate_chain" or pattern in ("delegate_ast", "neighbor_template"):
        visitors.append(VISITOR_DELEGATE)
    if layer == "dimension_clamp" or pattern == "dimension_clamp":
        visitors.append(VISITOR_LOOP)
    if any(kw in text for kw in LOOP_KEYWORDS):
        visitors.append(VISITOR_LOOP)
    if draft.fix_scope.co_fix_required:
        visitors.append(VISITOR_LOOP)

    expand = bool(draft.fix_scope.co_fix_required) or (
        VISITOR_LOOP in visitors
        and any(
            ac.criterion_role == "no_regression_sentinel"
            for ac in draft.acceptance_criteria
        )
    )

    if layer == "core_logic" and VISITOR_GUARD not in visitors:
        visitors.append(VISITOR_GUARD)

    visitors = list(dict.fromkeys(visitors))

    return AnalysisScope(
        files=files,
        classes=sorted(classes),
        methods=sorted(methods),
        visitors=visitors,
        expand_siblings=expand,
        missing_symbols=sorted(missing),
        context_domain=context_domain,
    )


def merge_scopes(
    base: AnalysisScope,
    plan: AnalysisScope | None,
    *,
    plan_confidence: float = 0.0,
) -> AnalysisScope:
    if plan is None:
        return base
    if plan_confidence < config.spec_parser_scope_merge_confidence_min:
        return base

    files = list(dict.fromkeys(plan.files + base.files))[
        : config.spec_parser_max_resolve_candidates
    ]
    classes = sorted(set(base.classes) | set(plan.classes))
    methods = sorted(set(base.methods) | set(plan.methods))
    visitors = list(dict.fromkeys(base.visitors + plan.visitors))
    expand = base.expand_siblings or plan.expand_siblings
    missing = sorted(set(base.missing_symbols) | set(plan.missing_symbols))
    domain = plan.context_domain or base.context_domain

    return AnalysisScope(
        files=files,
        classes=classes,
        methods=methods,
        visitors=visitors,
        expand_siblings=expand,
        missing_symbols=missing,
        context_domain=domain,
    )
