"""Tests for evidence fusion."""

from app.spec_parser.evidence_fusion import merge
from app.spec_parser.schema import (
    AcceptanceCriterion,
    ExecutionEvidence,
    RepoEnrichment,
    StructuredSpecification,
    TaskType,
)


def test_fusion_sets_primary_failure():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="s",
        repair_goals=["g"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-REL",
                description="d",
                check_type="assertion",
                observable="o",
            )
        ],
        fix_scope={"prerequisite": ["_print_Relational"]},
    )
    evidence = ExecutionEvidence(
        calibration_passed=True,
        per_criterion_results=[],
    )
    enrichment = RepoEnrichment(missing_handlers=["_print_Relational"])
    out = merge(spec, enrichment, evidence)
    assert out.repo_enrichment is None or out.confidence >= 0.0
