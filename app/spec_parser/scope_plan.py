"""Optional ScopePlan LLM with deterministic validation."""

from __future__ import annotations

import json
from dataclasses import dataclass

from loguru import logger

from app import config
from app.agents.agent_common import InvalidLLMResponse
from app.data_structures import MessageThread
from app.model.gpt import common
from app.spec_parser.schema import AnalysisScope, StructuredSpecification
from app.spec_parser.entity_extraction import EntityQuerySet, infer_primary_class
from app.spec_parser.scope_compiler import (
    VISITOR_DELEGATE,
    VISITOR_GUARD,
    VISITOR_LOOP,
    VISITOR_MISSING,
    compile_analysis_scope,
    merge_scopes,
)
from app.spec_parser.symbol_index import SymbolIndex
from app.spec_parser.target_resolution import FileCandidate

SCOPE_PLAN_SYSTEM = """You plan static code analysis scope for a bug-fix task.
Output ONLY valid JSON with keys:
focus_files (list of paths, MUST be from the candidate list),
focus_symbols (list of class/method names),
visitor_intents (subset of: missing_symbol, guard_raise, delegate_call, loop_bound),
expand_siblings (boolean),
confidence (0.0-1.0),
rationale_short (string, optional).
Do NOT invent file paths outside candidates. Do NOT suggest patches.
focus_files MUST include a file that defines the primary P1 entity as a class when applicable."""

INTENT_MAP = {
    "missing_symbol": VISITOR_MISSING,
    "guard_raise": VISITOR_GUARD,
    "delegate_call": VISITOR_DELEGATE,
    "loop_bound": VISITOR_LOOP,
}


@dataclass
class ScopePlanMeta:
    used_llm: bool = False
    fallback: bool = False
    raw_plan: dict | None = None
    validated: bool = False


def _format_scope_plan_user(
    draft: StructuredSpecification,
    candidates: list[FileCandidate],
    index: SymbolIndex,
) -> str:
    lines = [
        f"Summary: {draft.summary}",
        f"Repair goals: {draft.repair_goals}",
        f"Symptom goals: {draft.symptom_goals}",
        f"Architecture hint: layer={draft.architecture_hint.layer}, pattern={draft.architecture_hint.pattern}",
        "",
        "Candidate files (choose focus_files from this list only):",
    ]
    for c in candidates[:15]:
        methods = index.methods_in_file(c.rel_path)[:30]
        lines.append(f"- {c.rel_path} (score={c.score:.2f}) methods={methods}")
    entities = []
    if draft.failure_anchor:
        entities.extend(draft.failure_anchor.named_entities)
    for ac in draft.acceptance_criteria:
        if ac.covers_entity:
            entities.append(ac.covers_entity)
    lines.append("")
    lines.append(f"P1 entities: {entities}")
    lines.append("Produce ScopePlan JSON.")
    return "\n".join(lines)


def _intents_to_visitors(intents: list[str]) -> list[str]:
    out = [VISITOR_MISSING]
    for intent in intents:
        v = INTENT_MAP.get(intent)
        if v and v not in out:
            out.append(v)
    return out


def validate_scope_plan(
    plan_data: dict,
    candidates: list[FileCandidate],
    draft: StructuredSpecification,
    index: SymbolIndex,
    context_domain: str,
    entities: EntityQuerySet | None = None,
) -> AnalysisScope | None:
    candidate_paths = {c.rel_path for c in candidates}
    focus_files = [f for f in plan_data.get("focus_files", []) if f in candidate_paths]
    if not focus_files:
        return None

    if config.spec_parser_require_primary_class_in_scope:
        from app.spec_parser.entity_extraction import EntityQuerySet as EQS

        primary = infer_primary_class(entities or EQS(), draft)
        if primary and primary in index.classes:
            if not any(
                any(loc.rel_path == f for loc in index.classes[primary])
                for f in focus_files
            ):
                return None

    allowed_symbols: set[str] = set()
    if draft.failure_anchor:
        allowed_symbols.update(draft.failure_anchor.named_entities)
    for ac in draft.acceptance_criteria:
        if ac.covers_entity:
            allowed_symbols.add(ac.covers_entity)
    for f in focus_files:
        for m in index.methods_in_file(f):
            allowed_symbols.add(m)

    focus_symbols = [
        s
        for s in plan_data.get("focus_symbols", [])
        if any(s in a or a in s for a in allowed_symbols)
    ]
    visitors = _intents_to_visitors(plan_data.get("visitor_intents", []))
    expand = bool(plan_data.get("expand_siblings", False))

    classes: set[str] = set()
    methods: set[str] = set()
    for sym in focus_symbols:
        if "." in sym:
            methods.add(sym)
        else:
            classes.add(sym.split()[0])

    return AnalysisScope(
        files=focus_files,
        classes=sorted(classes),
        methods=sorted(methods),
        visitors=visitors,
        expand_siblings=expand,
        missing_symbols=[],
        context_domain=context_domain,
    )


def maybe_apply_scope_plan(
    draft: StructuredSpecification,
    candidates: list[FileCandidate],
    index: SymbolIndex,
    base_scope: AnalysisScope,
    entities: EntityQuerySet | None = None,
) -> tuple[AnalysisScope, ScopePlanMeta]:
    meta = ScopePlanMeta()
    if not config.spec_parser_scope_llm:
        return base_scope, meta

    meta.used_llm = True
    thread = MessageThread()
    thread.add_system(SCOPE_PLAN_SYSTEM)
    thread.add_user(_format_scope_plan_user(draft, candidates, index))

    try:
        response, *_ = common.SELECTED_MODEL.call(
            thread.to_msg(), response_format="json_object"
        )
        plan_data = json.loads(response)
        meta.raw_plan = plan_data
    except (InvalidLLMResponse, json.JSONDecodeError, Exception) as e:
        logger.warning("ScopePlan LLM failed: {}", e)
        meta.fallback = True
        return base_scope, meta

    validated = validate_scope_plan(
        plan_data,
        candidates,
        draft,
        index,
        base_scope.context_domain,
        entities=entities,
    )
    if validated is None:
        logger.warning("ScopePlan validation failed; using deterministic scope")
        meta.fallback = True
        return base_scope, meta

    meta.validated = True
    confidence = float(plan_data.get("confidence", 0.0))
    merged = merge_scopes(base_scope, validated, plan_confidence=confidence)
    return merged, meta
