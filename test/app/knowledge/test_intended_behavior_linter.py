"""Tests for intended_behavior_linter."""

from collections import defaultdict

from app.knowledge.intended_behavior_linter import has_blocking_findings, lint_localization


class _FakeBackend:
    project_path = "/tmp"

    def __init__(self):
        self.class_func_index = defaultdict(lambda: defaultdict(list))
        self.class_relation_index = defaultdict(list)


def test_scan_coverage_mismatch_blocks():
    backend = _FakeBackend()
    sibling_scan = [
        {
            "method_or_handler": "foo",
            "class": "A",
            "needs_fix": "yes",
            "anti_pattern_id": "AP-TEST",
        },
        {
            "method_or_handler": "bar",
            "class": "A",
            "needs_fix": "yes",
            "anti_pattern_id": "AP-TEST",
        },
    ]
    bug_locations_raw = [
        {
            "file": "a.py",
            "class": "A",
            "method": "foo",
            "intended_behavior": "fix foo",
            "spec_source": "scan_inferred",
            "spec_rationale": "scan says yes",
        }
    ]
    findings = lint_localization(
        backend,
        sibling_scan=sibling_scan,
        bug_locations_raw=bug_locations_raw,
        bug_locs=[],
        issue_text="issue",
        project_path="/tmp",
    )
    assert has_blocking_findings(findings)
    assert any(f.rule_id == "IB_SCAN_COVERAGE_MISMATCH" for f in findings)


def test_empty_scan_with_locations_blocks():
    backend = _FakeBackend()
    findings = lint_localization(
        backend,
        sibling_scan=[],
        bug_locations_raw=[
            {
                "file": "a.py",
                "class": "A",
                "method": "foo",
                "intended_behavior": "x",
                "spec_source": "issue_example",
                "spec_rationale": "r",
            }
        ],
        bug_locs=[],
        issue_text="",
        project_path="/tmp",
    )
    assert any(f.rule_id == "IB_SCAN_EMPTY_WITH_LOCATIONS" for f in findings)
