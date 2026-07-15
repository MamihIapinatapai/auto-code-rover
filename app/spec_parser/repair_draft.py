"""Behavioral repair intent for v3 reverse-TDD script generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.spec_parser.schema import (
    AcceptanceCriterion,
    ArchitectureHint,
    FixScope,
    NegativeConstraint,
    StructuredSpecification,
    TaskType,
)

REPAIR_DRAFT_FILENAME = "repair_draft.json"


class RepairDraft(BaseModel):
    """Behavioral repair intent for reverse-TDD script generation."""

    task_type: TaskType
    summary: str
    symptom_summary: str
    expected_behavior: list[str]
    observable_checks: list[AcceptanceCriterion]
    fix_scope: FixScope
    architecture_hint: ArchitectureHint
    negative_constraints: list[NegativeConstraint] = Field(default_factory=list)
    reporter_hints: list[str] = Field(default_factory=list)
    patch_hints: list[str] = Field(default_factory=list)
    inverse_tdd_notes: str = ""
    draft_source: Literal["p1_spec", "user_patch", "hybrid"] = "p1_spec"
    confidence: float = 0.0


def build_repair_draft(
    spec: StructuredSpecification, issue_text: str
) -> RepairDraft:
    del issue_text  # reserved for future patch_hints / keyword retrieval
    return RepairDraft(
        task_type=spec.task_type,
        summary=spec.summary,
        symptom_summary="; ".join(spec.symptom_goals) or spec.summary[:300],
        expected_behavior=list(spec.repair_goals),
        observable_checks=list(spec.acceptance_criteria),
        fix_scope=spec.fix_scope,
        architecture_hint=spec.architecture_hint,
        negative_constraints=list(spec.negative_constraints),
        reporter_hints=list(spec.issue_completeness.reporter_drafts),
        draft_source="p1_spec",
        confidence=spec.confidence,
    )


def save_repair_draft(output_dir: Path | str, draft: RepairDraft) -> Path:
    path = Path(output_dir) / REPAIR_DRAFT_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(draft.model_dump_json(indent=2))
    return path


def load_repair_draft(output_dir: Path | str) -> RepairDraft | None:
    path = Path(output_dir) / REPAIR_DRAFT_FILENAME
    if not path.exists():
        return None
    return RepairDraft.model_validate(json.loads(path.read_text()))
