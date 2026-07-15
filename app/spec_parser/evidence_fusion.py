"""Fuse static and dynamic evidence into final specification."""

from __future__ import annotations

from app.spec_parser.schema import (
    ExecutionEvidence,
    FailureAnchor,
    RepoEnrichment,
    StructuredSpecification,
)


def merge_v3(
    spec: StructuredSpecification,
    evidence: ExecutionEvidence | None,
) -> StructuredSpecification:
    """P6 fusion for v3: dynamic evidence + P1 contract only."""
    return merge(spec, None, evidence)


def merge(
    spec: StructuredSpecification,
    enrichment: RepoEnrichment | None,
    evidence: ExecutionEvidence | None,
) -> StructuredSpecification:
    out = spec.model_copy(deep=True)
    confidence = out.confidence

    if enrichment and enrichment.missing_handlers and evidence:
        if evidence.primary_failure_ac_id:
            for prereq in out.fix_scope.prerequisite:
                if "Relational" in prereq and evidence.primary_failure_ac_id in (
                    "AC-REL",
                    "AC-002",
                ):
                    confidence = min(1.0, confidence + 0.15)
                    break

    if evidence:
        out.execution_evidence = evidence
        if not evidence.calibration_passed:
            out.confidence = max(0.1, confidence * 0.5)
        elif evidence.per_criterion_results:
            first_fail = next(
                (
                    cr.criterion_id
                    for cr in evidence.per_criterion_results
                    if not cr.passed_on_buggy_code and cr.expected_failure
                ),
                None,
            )
            if first_fail and not evidence.primary_failure_ac_id:
                out.execution_evidence = evidence.model_copy(
                    update={"primary_failure_ac_id": first_fail}
                )
            out = _promote_failed_ac_entities(out)
            if out.failure_anchor is None:
                out.failure_anchor = FailureAnchor(anchor_type="assertion_error")
            if evidence.calibration_error and out.failure_anchor:
                out.failure_anchor.exception_type = evidence.calibration_error
            if evidence.calibration_passed:
                confidence = min(1.0, confidence + 0.05)

    out.confidence = confidence
    return out


def _promote_failed_ac_entities(spec: StructuredSpecification) -> StructuredSpecification:
    ee = spec.execution_evidence
    if ee is None or not ee.primary_failure_ac_id:
        return spec
    ac_id = ee.primary_failure_ac_id
    for ac in spec.acceptance_criteria:
        if ac.id != ac_id or not ac.covers_entity:
            continue
        if spec.failure_anchor is None:
            spec.failure_anchor = FailureAnchor(anchor_type="assertion_error")
        entities = list(spec.failure_anchor.named_entities)
        if ac.covers_entity not in entities:
            entities.insert(0, ac.covers_entity)
            spec.failure_anchor = spec.failure_anchor.model_copy(
                update={"named_entities": entities}
            )
        break
    return spec
