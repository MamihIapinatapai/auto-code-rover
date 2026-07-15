"""Shared working memory persistence."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.spec_parser.schema import SharedWorkingMemory, StructuredSpecification
from app.task import Task


class SharedMemoryStore:
    FILENAME = "shared_working_memory.json"
    SEARCH_CONTEXT_FILENAME = "search_context.txt"
    REPO_ENRICHMENT_FILENAME = "repo_enrichment.json"
    TARGET_RESOLUTION_FILENAME = "target_resolution.json"
    SCOPE_PLAN_FILENAME = "scope_plan.json"
    EXECUTION_EVIDENCE_FILENAME = "execution_evidence.json"
    SPEC_FUSION_FILENAME = "spec_fusion.json"

    @staticmethod
    def write(output_dir: Path | str, swm: SharedWorkingMemory) -> Path:
        path = Path(output_dir) / SharedMemoryStore.FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(swm.model_dump_json(indent=2))
        return path

    @staticmethod
    def read(output_dir: Path | str) -> SharedWorkingMemory | None:
        path = Path(output_dir) / SharedMemoryStore.FILENAME
        if not path.exists():
            return None
        return SharedWorkingMemory.model_validate_json(path.read_text())

    @staticmethod
    def build_from_task(
        task: Task, issue_text: str, spec: StructuredSpecification
    ) -> SharedWorkingMemory:
        repo = getattr(task, "repo", None) or getattr(task, "project_name", "unknown")
        return SharedWorkingMemory(
            instance_id=task.task_id,
            repo=str(repo),
            problem_statement_hash=hashlib.sha256(issue_text.encode()).hexdigest()[:16],
            structured_spec=spec,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def write_sidecar_artifacts(
        output_dir: Path | str, spec: StructuredSpecification
    ) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        if spec.repo_enrichment is not None:
            (out / SharedMemoryStore.REPO_ENRICHMENT_FILENAME).write_text(
                spec.repo_enrichment.model_dump_json(indent=2)
            )
        if spec.execution_evidence is not None:
            (out / SharedMemoryStore.EXECUTION_EVIDENCE_FILENAME).write_text(
                spec.execution_evidence.model_dump_json(indent=2)
            )
        fusion_summary = {
            "repair_goals": spec.repair_goals,
            "fix_scope": spec.fix_scope.model_dump(),
            "architecture_hint": spec.architecture_hint.model_dump(),
            "confidence": spec.confidence,
        }
        (out / SharedMemoryStore.SPEC_FUSION_FILENAME).write_text(
            __import__("json").dumps(fusion_summary, indent=2)
        )
        ctx = SharedMemoryStore.to_search_context_from_spec(spec)
        (out / SharedMemoryStore.SEARCH_CONTEXT_FILENAME).write_text(ctx)

    @staticmethod
    def to_search_context(swm: SharedWorkingMemory) -> str:
        return SharedMemoryStore.to_search_context_from_spec(swm.structured_spec)

    @staticmethod
    def to_search_context_from_spec(spec: StructuredSpecification) -> str:
        lines = [
            "=== Repair Contract (Specification Parsing Agent) ===",
            f"Task Type: {spec.task_type.value}",
            f"Summary: {spec.summary}",
        ]
        if spec.execution_evidence and not spec.execution_evidence.calibration_passed:
            lines.extend(
                [
                    "",
                    "## Calibration Status",
                    "calibration_passed: false",
                    f"reason: {spec.execution_evidence.calibration_error or 'validation failed'}",
                ]
            )

        lines.extend(["", "## Repair Goals (authoritative)"])
        for g in spec.repair_goals:
            lines.append(f"- {g}")

        if spec.symptom_goals:
            lines.append("")
            lines.append("## Symptom Goals (context only)")
            for g in spec.symptom_goals:
                lines.append(f"- {g}")

        fs = spec.fix_scope
        if any([fs.in_scope, fs.out_of_scope, fs.co_fix_required, fs.prerequisite]):
            lines.append("")
            lines.append("## Fix Scope")
            if fs.in_scope:
                lines.append("in_scope: " + ", ".join(fs.in_scope))
            if fs.co_fix_required:
                lines.append("co_fix_required: " + ", ".join(fs.co_fix_required))
            if fs.prerequisite:
                lines.append("prerequisite: " + ", ".join(fs.prerequisite))
            if fs.out_of_scope:
                lines.append("out_of_scope: " + ", ".join(fs.out_of_scope))

        ah = spec.architecture_hint
        if ah.layer != "unknown" or ah.neighbor_reference:
            lines.append("")
            lines.append("## Architecture Hint")
            lines.append(f"layer: {ah.layer}, pattern: {ah.pattern}")
            if ah.neighbor_reference:
                lines.append(f"neighbor_reference: {ah.neighbor_reference}")

        if spec.negative_constraints:
            lines.append("")
            lines.append("## Negative Constraints")
            for nc in spec.negative_constraints:
                lines.append(f"- {nc.description} ({nc.rationale})")

        if spec.acceptance_criteria:
            lines.append("")
            lines.append("## Acceptance Criteria")
            for ac in spec.acceptance_criteria:
                lines.append(
                    f"- [{ac.id}] {ac.priority} {ac.criterion_role}: {ac.observable}"
                )

        if spec.execution_evidence:
            ee = spec.execution_evidence
            lines.append("")
            lines.append("## Execution Evidence (buggy codebase)")
            if ee.primary_failure_ac_id:
                lines.append(f"primary_failure_ac_id: {ee.primary_failure_ac_id}")
            for cr in ee.per_criterion_results:
                lines.append(
                    f"- {cr.criterion_id}: passed_on_buggy={cr.passed_on_buggy_code}"
                )

        if spec.failure_anchor and spec.failure_anchor.named_entities:
            lines.append("")
            lines.append("## Failure Anchor Entities")
            lines.append(", ".join(spec.failure_anchor.named_entities))

        if spec.parser_version.startswith("3"):
            symptom_summary = "; ".join(spec.symptom_goals) or spec.summary[:300]
            lines.append("")
            lines.append("## Repair Draft (v3 behavioral intent)")
            lines.append(f"symptom_summary: {symptom_summary}")
            if spec.repair_goals:
                lines.append("expected_behavior:")
                for goal in spec.repair_goals:
                    lines.append(f"- {goal}")

        if spec.repo_enrichment:
            re = spec.repo_enrichment
            if re.target_files:
                lines.append("")
                lines.append("## Target Files (P2 static scope, ranked)")
                for i, tf in enumerate(re.target_files[:5], start=1):
                    lines.append(f"{i}. {tf}")
            primary = None
            preferred_file = None
            if spec.failure_anchor and spec.failure_anchor.named_entities:
                primary = spec.failure_anchor.named_entities[0]
            if re.target_files:
                preferred_file = re.target_files[0]
            if primary or preferred_file:
                lines.append("")
                lines.append("## Primary Anchor")
                if primary:
                    lines.append(f"entity: {primary}")
                if preferred_file:
                    lines.append(f"preferred_file: {preferred_file}")
            if re.context_domain:
                lines.append("")
                lines.append("## Context Domain")
                lines.append(re.context_domain)
            if re.missing_handlers:
                lines.append("")
                lines.append("## Static: Missing Handlers")
                lines.append(", ".join(re.missing_handlers))
            neighbor = re.neighbor_reference or spec.architecture_hint.neighbor_reference
            if neighbor:
                lines.append(f"neighbor_reference: {neighbor}")
            if re.search_api_hints:
                lines.append(
                    "search_api_hints: " + ", ".join(re.search_api_hints[:15])
                )
            max_snip = config.spec_parser_search_context_max_snippet_chars
            if re.evidence_snippets:
                lines.append("")
                lines.append("## Static Evidence (snippet)")
                for key, text in list(re.evidence_snippets.items())[:2]:
                    snippet = text[:max_snip].replace("\n", " ")
                    lines.append(f"{key}: {snippet}")

        if spec.issue_completeness.reporter_drafts:
            lines.append("")
            lines.append("## Reporter Drafts (non-authoritative)")
            for draft in spec.issue_completeness.reporter_drafts[:3]:
                lines.append(f"- {draft[:200]}")

        return "\n".join(lines)
