"""Tests for v3.3 evidence-chain helpers."""

from app.spec_parser.evidence_chain import (
    migrate_alignment_to_chain,
    parse_coverage_items,
    sanitize_coverage_items,
    summarize_coverage,
)
from app.spec_parser.schema import IssueCoverageItem, ReviewIssueGap
from app.spec_parser.script_reviewer import _is_illegal_rewrite, parse_review_response


def test_migrate_alignment_to_chain():
    gaps = [
        ReviewIssueGap(kind="missing_must", detail="CLI group missing"),
        ReviewIssueGap(kind="weak_assert", detail="only dict keys"),
    ]
    items = migrate_alignment_to_chain(gaps)
    assert len(items) == 2
    assert items[0].verdict == "missing"
    assert items[1].verdict == "partial"


def test_sanitize_demotes_covered_weak():
    items = [
        IssueCoverageItem(
            issue_item_id="I1",
            verdict="covered",
            assertion_strength="weak",
            legal_rewrite="assert x == 1",
        )
    ]
    kept, _, changed = sanitize_coverage_items(
        items, is_illegal_rewrite=_is_illegal_rewrite
    )
    assert changed
    assert kept[0].verdict == "partial"


def test_parse_review_includes_coverage_chain():
    text = """
{
  "diagnosis": {"failure_class": "lint", "summary": "L10"},
  "blocking_fixes": [],
  "gate_fixes": [],
  "issue_alignment": [],
  "issue_coverage_chain": [
    {
      "issue_item_id": "I7",
      "issue_quote": "Add snapshot CLI group",
      "ac_id": "AC-007",
      "expected_layer": "cli",
      "actual_layer": "api",
      "assertion_strength": "wrong_layer",
      "verdict": "partial",
      "legal_rewrite": "from click.testing import CliRunner\\nrunner = CliRunner()"
    }
  ],
  "decision_summary": {"recommended_priority": "lint_first"},
  "deferred_issue_gaps": [],
  "ordered_actions": ["1. Fix L10"]
}
"""
    report = parse_review_response(text, stage="preflight", round_no=1)
    assert report.parse_ok
    assert len(report.issue_coverage_chain) == 1
    assert report.issue_coverage_chain[0].issue_item_id == "I7"
    assert report.decision_summary.get("recommended_priority") == "lint_first"


def test_summarize_coverage():
    items = parse_coverage_items(
        [
            {"verdict": "covered"},
            {"verdict": "missing"},
            {"verdict": "partial"},
        ]
    )
    summary = summarize_coverage(items)
    assert summary["covered"] == 1
    assert summary["missing"] == 1
    assert summary["partial"] == 1
