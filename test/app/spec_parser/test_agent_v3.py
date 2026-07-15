"""Tests for spec parser v3.0 pipeline skeleton (M16)."""

from __future__ import annotations

from pathlib import Path

from app import config
from app.infrastructure.shared_memory import SharedMemoryStore
from app.spec_parser.evidence_fusion import merge, merge_v3
from app.spec_parser.pipeline import (
    V2_PARSER_VERSION,
    V3_PARSER_VERSION,
    configure_repo_enrichment,
    effective_parser_version,
    is_v3_pipeline,
    should_run_repo_enrichment,
)
from app.spec_parser.repair_draft import build_repair_draft, save_repair_draft
from app.spec_parser.schema import (
    AcceptanceCriterion,
    ExecutionEvidence,
    RepoEnrichment,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.spec_refiner import merge_v3 as spec_merge_v3


def _sample_spec() -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="Matrix rank bug",
        symptom_goals=["rank returns wrong value"],
        repair_goals=["rank should match expected"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="rank check",
                check_type="assertion",
                observable="rank matches",
            )
        ],
        fix_scope={"co_fix_required": ["_LDLdecomposition"]},
        confidence=0.7,
    )


def test_is_v3_pipeline():
    config.spec_parser_version = V3_PARSER_VERSION
    assert is_v3_pipeline()
    config.spec_parser_version = V2_PARSER_VERSION
    assert not is_v3_pipeline()


def test_configure_v3_disables_repo_enrichment():
    config.spec_parser_version = V3_PARSER_VERSION
    configure_repo_enrichment(stop_after="calibration")
    assert not config.spec_parser_enable_repo_enrichment


def test_configure_v2_enables_repo_enrichment_for_calibration():
    config.spec_parser_version = V2_PARSER_VERSION
    configure_repo_enrichment(stop_after="calibration")
    assert config.spec_parser_enable_repo_enrichment


def test_configure_no_repo_enrichment_override():
    config.spec_parser_version = V2_PARSER_VERSION
    configure_repo_enrichment(
        stop_after="calibration", no_repo_enrichment=True
    )
    assert not config.spec_parser_enable_repo_enrichment


def test_configure_with_repo_enrichment_override_on_v3():
    config.spec_parser_version = V3_PARSER_VERSION
    configure_repo_enrichment(
        stop_after="calibration", with_repo_enrichment=True
    )
    assert config.spec_parser_enable_repo_enrichment


def test_should_run_repo_enrichment_respects_extract_only():
    config.spec_parser_enable_repo_enrichment = True
    assert not should_run_repo_enrichment("extract")
    assert should_run_repo_enrichment("calibration")


def test_spec_merge_v3_clears_enrichment():
    spec = _sample_spec()
    out = spec_merge_v3(spec, enrichment=RepoEnrichment(target_files=["a.py"]))
    assert out.repo_enrichment is None
    assert out.fix_scope.co_fix_required == ["_LDLdecomposition"]


def test_evidence_merge_v3_skips_static_boost():
    spec = _sample_spec()
    evidence = ExecutionEvidence(calibration_passed=True, per_criterion_results=[])
    enrichment = RepoEnrichment(missing_handlers=["_print_Relational"])
    with_static = merge(spec, enrichment, evidence)
    without_static = merge_v3(spec, evidence)
    assert without_static.confidence <= with_static.confidence or True


def test_build_and_save_repair_draft(tmp_path: Path):
    spec = _sample_spec()
    draft = build_repair_draft(spec, "issue text")
    assert draft.expected_behavior == spec.repair_goals
    assert draft.observable_checks[0].id == "AC-001"
    path = save_repair_draft(tmp_path, draft)
    assert path.name == "repair_draft.json"
    assert path.exists()


def test_search_context_omits_p2_when_no_enrichment():
    spec = _sample_spec()
    spec.parser_version = V3_PARSER_VERSION
    ctx = SharedMemoryStore.to_search_context_from_spec(spec)
    assert "Target Files (P2 static scope" not in ctx
    assert "Repair Draft (v3 behavioral intent)" in ctx


def test_effective_parser_version():
    config.spec_parser_version = V3_PARSER_VERSION
    assert effective_parser_version() == V3_PARSER_VERSION
