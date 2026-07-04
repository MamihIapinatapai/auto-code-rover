"""Fuse static and dynamic evidence into final specification."""

from __future__ import annotations

from app.spec_parser.schema import (
    ExecutionEvidence,
    FailureAnchor,
    RepoEnrichment,
    StructuredSpecification,
)


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
                if "Relational" in prereq and evidence.primary_failure_ac_id == "AC-REL":
                    confidence = min(1.0, confidence + 0.15)
                    break

    if evidence and evidence.calibration_passed and evidence.per_criterion_results:
        first_fail = next(
            (
                cr.criterion_id
                for cr in evidence.per_criterion_results
                if not cr.passed_on_buggy_code and cr.expected_failure
            ),
            None,
        )
        if first_fail and not evidence.primary_failure_ac_id:
            evidence = evidence.model_copy(update={"primary_failure_ac_id": first_fail})
        out.execution_evidence = evidence

        if out.failure_anchor is None:
            out.failure_anchor = FailureAnchor(anchor_type="assertion_error")
        if evidence.calibration_error:
            out.failure_anchor.exception_type = evidence.calibration_error

    out.confidence = confidence
    return out
