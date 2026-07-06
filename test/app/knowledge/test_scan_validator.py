"""Tests for scan_validator (HB)."""

from collections import defaultdict

from app.knowledge.scan_validator import validate_sibling_scan


class _FakeBackend:
    project_path = "/tmp"
    class_relation_index = defaultdict(list)

    def __init__(self):
        self.class_func_index = defaultdict(lambda: defaultdict(list))
        self.class_func_index["Matrix"] = {
            "_eval_is_upper": [("sympy/matrices/matrices.py", (1, 10))],
        }


def test_scan_row_not_found():
    backend = _FakeBackend()
    findings = validate_sibling_scan(
        backend,
        [{"method_or_handler": "missing_method", "class": "Matrix", "needs_fix": "yes"}],
    )
    assert any(f.rule_id == "SCAN_ROW_NOT_FOUND" for f in findings)
