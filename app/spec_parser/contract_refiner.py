"""Deterministic post-processing of P1 structured spec (repo-agnostic)."""

from __future__ import annotations

import re

from app.spec_parser.schema import (
    ArchitectureHint,
    NegativeConstraint,
    StructuredSpecification,
)

_RELATIONAL_TOKENS = ("Ne(", "Eq(", "Relational", "_print_Relational")
_PIECEWISE_TOKENS = ("Piecewise(", "piecewise")
_PRINT_LAYERS = frozenset({"formatter", "delegate_chain"})


def refine(draft: StructuredSpecification, issue_text: str) -> StructuredSpecification:
    out = draft.model_copy(deep=True)
    out = _infer_prerequisites_from_reporter_drafts(out, issue_text)
    out = _split_symptom_vs_repair_layers(out, issue_text)
    out = _demote_reporter_scope_creep(out)
    return out


def _text_blob(spec: StructuredSpecification, issue_text: str) -> str:
    parts = list(spec.issue_completeness.reporter_drafts) + [issue_text]
    return "\n".join(parts)


def _infer_prerequisites_from_reporter_drafts(
    spec: StructuredSpecification, issue_text: str
) -> StructuredSpecification:
    blob = _text_blob(spec, issue_text)
    layer = spec.architecture_hint.layer
    fs = spec.fix_scope.model_copy(deep=True)

    if any(tok in blob for tok in _RELATIONAL_TOKENS):
        if layer in _PRINT_LAYERS or "ccode" in blob.lower() or "print" in blob.lower():
            prereq = "_print_Relational"
            if prereq not in fs.prerequisite:
                fs.prerequisite.append(prereq)

    if any(tok in blob for tok in _PIECEWISE_TOKENS):
        ah = spec.architecture_hint.model_copy(deep=True)
        if ah.pattern == "unknown":
            ah.pattern = "delegate_ast"
        if ah.layer == "unknown":
            ah.layer = "formatter"
        spec.architecture_hint = ah
        desc = "Do not use inline single-line ternary for codegen output"
        if not any(nc.description == desc for nc in spec.negative_constraints):
            spec.negative_constraints.append(
                NegativeConstraint(
                    description=desc,
                    rationale="Issue suggests Piecewise delegation pattern",
                )
            )

    spec.fix_scope = fs
    return spec


def _split_symptom_vs_repair_layers(
    spec: StructuredSpecification, issue_text: str
) -> StructuredSpecification:
    blob = (issue_text + " " + " ".join(spec.symptom_goals)).lower()
    if "pretty" in blob and "latex" in blob and "inconsistent" in blob:
        desc = "Do not modify the pretty printer (reference output is correct)"
        if not any(nc.description == desc for nc in spec.negative_constraints):
            spec.negative_constraints.append(
                NegativeConstraint(
                    description=desc,
                    rationale="Symptom compares LaTeX to pretty printer",
                )
            )
        out_scope = "pretty printer modifications"
        fs = spec.fix_scope.model_copy(deep=True)
        if out_scope not in fs.out_of_scope:
            fs.out_of_scope.append(out_scope)
        spec.fix_scope = fs
        ah = spec.architecture_hint.model_copy(deep=True)
        if ah.layer == "formatter":
            ah.layer = "bracket_decision"
        spec.architecture_hint = ah

    return spec


def _demote_reporter_scope_creep(spec: StructuredSpecification) -> StructuredSpecification:
    must_entities = {
        ac.covers_entity.lower()
        for ac in spec.acceptance_criteria
        if ac.priority == "must" and ac.covers_entity
    }
    repair = list(spec.repair_goals)
    demoted: list[str] = []
    kept: list[str] = []

    for goal in repair:
        lower = goal.lower()
        entity_hits = [
            e
            for e in must_entities
            if e in lower or re.search(rf"\b{re.escape(e)}\b", lower)
        ]
        if entity_hits or len(repair) <= 1:
            kept.append(goal)
            continue
        if "float" in lower and not any("float" in e for e in must_entities):
            demoted.append(goal)
            fs = spec.fix_scope.model_copy(deep=True)
            label = "Float formatting (reporter draft, not must AC)"
            if label not in fs.out_of_scope:
                fs.out_of_scope.append(label)
            spec.fix_scope = fs
        else:
            kept.append(goal)

    if demoted and kept:
        spec.repair_goals = kept
        for g in demoted:
            if g not in spec.symptom_goals:
                spec.symptom_goals.append(g)

    return spec
