"""Orchestrate generic static enrichment (v2.0)."""

from __future__ import annotations

import json
from pathlib import Path

from app.spec_parser.entity_extraction import collect_entities
from app.spec_parser.generic_enrichment import run_generic_enrichment
from app.spec_parser.issue_symbol_coverage import (
    symbols_in_issue_text,
    uncovered_handlers_in_scope,
)
from app.spec_parser.repo_context import RepoContext
from app.spec_parser.schema import (
    RepoEnrichment,
    ScopePlanRecord,
    StructuredSpecification,
    TargetResolutionArtifact,
)
from app.spec_parser.scope_compiler import compile_analysis_scope
from app.spec_parser.scope_plan import maybe_apply_scope_plan
from app.spec_parser.symbol_index import build_symbol_index
from app.spec_parser.target_resolution import infer_context_domain, resolve_target_files
from app.task import Task

TARGET_RESOLUTION_FILENAME = "target_resolution.json"
SCOPE_PLAN_FILENAME = "scope_plan.json"


def run(
    task: Task,
    issue_text: str,
    repo_ctx: RepoContext,
    draft: StructuredSpecification,
    output_dir: Path | str | None = None,
) -> tuple[RepoEnrichment, TargetResolutionArtifact]:
    del repo_ctx  # reserved for future repo metadata
    index = build_symbol_index(task.project_path)
    entities = collect_entities(issue_text, draft, index=index)
    candidates = resolve_target_files(task.project_path, entities, index, draft=draft)
    domain = infer_context_domain(candidates)
    base_scope = compile_analysis_scope(draft, candidates, index, domain)
    scope, plan_meta = maybe_apply_scope_plan(
        draft, candidates, index, base_scope, entities=entities
    )
    enrichment = run_generic_enrichment(task, scope, draft, index, issue_text=issue_text)

    issue_symbols = symbols_in_issue_text(
        issue_text, draft.issue_completeness.reporter_drafts
    )
    uncovered = uncovered_handlers_in_scope(
        issue_symbols, scope.files, task.project_path, index
    )
    if uncovered:
        merged_missing = set(enrichment.missing_handlers) | set(uncovered)
        enrichment = enrichment.model_copy(
            update={"missing_handlers": sorted(merged_missing)}
        )

    artifact = TargetResolutionArtifact(
        entities=[
            {
                "name": q.name,
                "kind": q.kind,
                "source": q.source,
                "weight": q.weight,
                "is_primary": q.is_primary,
            }
            for q in entities.queries
        ],
        candidates=[
            {
                "rel_path": c.rel_path,
                "score": c.score,
                "matched_entities": c.matched_entities,
            }
            for c in candidates
        ],
        analysis_scope=scope,
        scope_plan=ScopePlanRecord(
            used_llm=plan_meta.used_llm,
            fallback=plan_meta.fallback,
            validated=plan_meta.validated,
            raw_plan=plan_meta.raw_plan,
        ),
    )

    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / TARGET_RESOLUTION_FILENAME).write_text(
            artifact.model_dump_json(indent=2)
        )
        if plan_meta.raw_plan is not None:
            (out / SCOPE_PLAN_FILENAME).write_text(
                json.dumps(
                    {
                        "raw_plan": plan_meta.raw_plan,
                        "used_llm": plan_meta.used_llm,
                        "fallback": plan_meta.fallback,
                        "validated": plan_meta.validated,
                    },
                    indent=2,
                )
            )

    return enrichment, artifact
