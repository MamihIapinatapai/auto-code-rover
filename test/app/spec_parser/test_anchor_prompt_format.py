"""Prompt injection for ScriptAnchor."""

from app.spec_parser.schema import (
    AcceptanceCriterion,
    RepoContext,
    StructuredSpecification,
    TaskType,
)
from app.spec_parser.script_prompts_v3 import format_script_user_v3
from app.spec_parser.pipeline import apply_spec_parser_version
from app import config


def test_format_script_user_includes_anchor_block():
    spec = StructuredSpecification(
        task_type=TaskType.FEATURE,
        summary="x",
        repair_goals=["y"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-001",
                description="d",
                check_type="assertion",
                observable="o",
            )
        ],
    )
    ctx = RepoContext(repo_name="demo", test_framework="pytest", top_level_packages=["pkg"])
    text = format_script_user_v3(
        spec,
        ctx,
        "issue text about Retort",
        "test_feature.py",
        None,
        1,
        script_anchor_block="## ScriptAnchor\n- Retort AST: (self, *, recipe=())",
    )
    assert "ScriptAnchor" in text
    assert "recipe=()" in text


def test_apply_version_331_enables_anchor():
    apply_spec_parser_version("3.3.1")
    assert config.spec_parser_enable_script_anchor is True
    assert config.spec_parser_enable_script_anchor_tier2 is True
    apply_spec_parser_version("3.3.0")
    assert config.spec_parser_enable_script_anchor is False
