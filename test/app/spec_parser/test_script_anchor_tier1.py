"""Tier1 ScriptAnchor tests — fixtures mirror adaptix Retort / CLI evidence."""

from pathlib import Path

from app.spec_parser.schema import (
    AcceptanceCriterion,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_anchor import (
    build_tier1,
    detect_layer_gaps,
    format_anchor_for_prompt,
)


def _demo_repo(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "retort.py").write_text(
        '''
class Retort:
    """Retort factory."""
    def __init__(self, *, recipe=(), strict_coercion=True):
        """Create retort with recipe."""
        self.recipe = recipe
    def load(self, data):
        return data
'''
    )
    (pkg / "cli.py").write_text(
        "def main():\n    print('ok')\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ndemo-cli = "pkg.cli:main"\n'
    )
    # decoy in tests — must NOT win
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_retort.py").write_text(
        "class Retort:\n    def __init__(self, name_mapping=None):\n        pass\n"
    )
    return tmp_path


def _spec() -> StructuredSpecification:
    return StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="aliases via Retort",
        repair_goals=["support Retort recipe aliases"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Retort recipe",
                check_type="assertion",
                observable="Retort(recipe=[...])",
                covers_entity="Retort",
            )
        ],
    )


def test_tier1_locates_retort_not_test_decoy(tmp_path: Path):
    root = _demo_repo(tmp_path)
    issue = "Use Retort with recipe mapping for aliases. Add CLI via demo-cli."
    anchor = build_tier1(
        project_path=str(root),
        issue_text=issue,
        spec=_spec(),
        package_roots=["pkg"],
    )
    assert anchor.tier1_ok
    retorts = [s for s in anchor.symbols if "Retort" in s.name]
    assert retorts, anchor.symbols
    sym = retorts[0]
    assert "test" not in sym.rel_path.lower()
    assert "recipe" in sym.signature_ast
    assert "name_mapping" not in sym.signature_ast
    assert any(ep.name == "demo-cli" for ep in anchor.entrypoints)
    assert anchor.layer_hints.get("cli") == "present"


def test_format_omits_low_confidence_signature():
    from app.spec_parser.schema import AnchorSymbol, ScriptAnchor

    anchor = ScriptAnchor(
        symbols=[
            AnchorSymbol(
                name="Foo",
                kind="class",
                rel_path="a.py",
                signature_ast="(self, bad=1)",
                confidence=0.3,
                ambiguous=False,
            )
        ],
        tier1_ok=True,
    )
    text = format_anchor_for_prompt(anchor)
    assert "omitted" in text.lower() or "low confidence" in text.lower()
    assert "bad=1" not in text


def test_layer_gap_when_cli_in_issue_but_no_entry(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "lib.py").write_text("class Monitor:\n    pass\n")
    spec = StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="x",
        repair_goals=["cli"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="Monitor",
                check_type="assertion",
                observable="Monitor",
                covers_entity="Monitor",
            )
        ],
    )
    anchor = build_tier1(
        project_path=str(tmp_path),
        issue_text="Add snapshot CLI group for Monitor",
        spec=spec,
        package_roots=["pkg"],
    )
    gaps = detect_layer_gaps("Add snapshot CLI group for Monitor", anchor)
    assert "LAYER_GAP_CLI" in gaps
