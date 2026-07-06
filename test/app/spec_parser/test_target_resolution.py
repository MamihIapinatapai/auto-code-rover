"""Tests for entity→file resolution (M10)."""

from pathlib import Path

from app.spec_parser.entity_extraction import collect_entities, infer_primary_class
from app.spec_parser.schema import (
    AcceptanceCriterion,
    FailureAnchor,
    FixScope,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.symbol_index import build_symbol_index
from app.spec_parser.target_resolution import resolve_target_files


def _minimal_spec(**kwargs) -> StructuredSpecification:
    defaults = dict(
        task_type=TaskType.BUG_FIX,
        summary="test",
        repair_goals=["fix Permutation constructor"],
        failure_anchor=FailureAnchor(
            anchor_type="inferred",
            named_entities=["Permutation constructor"],
        ),
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="overlap cycles",
                check_type="assertion",
                observable="Permutation([[0,1],[0,1]])",
                priority="must",
                covers_entity="Permutation",
                criterion_role="fail_to_pass",
            )
        ],
        fix_scope=FixScope(in_scope=["Permutation"]),
    )
    defaults.update(kwargs)
    return StructuredSpecification(**defaults)


def test_bound_init_prefers_class_file(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text(
        "class Permutation:\n    def __init__(self, cycles):\n        pass\n"
    )
    (pkg / "b.py").write_text("class Foo:\n    def __init__(self):\n        pass\n")
    issue = "Permutation([[0,1],[0,1]]) fails"
    spec = _minimal_spec()
    index = build_symbol_index(str(tmp_path))
    entities = collect_entities(issue, spec, index=index)
    assert any("Permutation.__init__" == q.name for q in entities.queries)
    assert not any(q.name == "__init__" and q.kind == "method" for q in entities.queries)
    candidates = resolve_target_files(str(tmp_path), entities, index, draft=spec)
    assert candidates
    assert "pkg/a.py" in candidates[0].rel_path


def test_issue_class_stoplist(tmp_path):
    issue = "If I call Permutation([[0,1],[0,1]])"
    spec = _minimal_spec()
    index = build_symbol_index(str(tmp_path))
    entities = collect_entities(issue, spec, index=index)
    names = {q.name for q in entities.queries}
    assert "If" not in names
    assert "I" not in names


def test_infer_primary_class():
    spec = _minimal_spec()
    from app.spec_parser.entity_extraction import EntityQuery, EntityQuerySet

    entities = EntityQuerySet(
        queries=[
            EntityQuery(
                name="Permutation",
                kind="class",
                source="p1_named",
                is_primary=True,
            )
        ]
    )
    assert infer_primary_class(entities, spec) == "Permutation"
