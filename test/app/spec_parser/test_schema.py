"""Unit tests for spec parser schema."""

import pytest
from pydantic import ValidationError

from app.spec_parser.schema import (
    AcceptanceCriterion,
    FixScope,
    StructuredSpecification,
    TaskType,
)


def test_structured_spec_minimal_valid():
    spec = StructuredSpecification(
        task_type=TaskType.BUG_FIX,
        summary="Fix Permutation overlap",
        repair_goals=["Allow non-disjoint cycles"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="overlap",
                check_type="assertion",
                observable="Permutation([[0,1],[0,1]]) is identity",
            )
        ],
    )
    assert spec.task_type == TaskType.BUG_FIX
    assert len(spec.repair_goals) == 1


def test_fix_scope_defaults():
    fs = FixScope()
    assert fs.in_scope == []
    assert fs.co_fix_required == []


def test_repair_goals_required():
    with pytest.raises(ValidationError):
        StructuredSpecification(
            task_type=TaskType.BUG_FIX,
            summary="x",
            repair_goals=[],
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="AC-001",
                    description="d",
                    check_type="assertion",
                    observable="o",
                )
            ],
        )
