"""Tests for ContractFeatureSet (HC v1)."""

from app.knowledge.contract_features import (
    callee_jaccard,
    contracts_conflict,
    extract_from_intended_behavior,
    extract_from_source,
)


def test_extract_self_print_delegation():
    source = '''
def _print_Foo(self, expr):
    return "Hold[" + self._print(expr.args[0]) + "]"
'''
    fs = extract_from_source(source, "_print_Foo")
    assert fs is not None
    assert fs.has_self_print
    assert "_print" in fs.callees


def test_contracts_conflict_issue_follows_issue_not_neighbor():
    issue = "```python\ndef f():\n    return expr.stringify(x)\n```"
    from app.knowledge.contract_features import extract_from_issue

    issue_fs = extract_from_issue(issue)
    neighbor_fs = extract_from_source(
        "def _print_Foo(self, e):\n    return self._print(e)", "_print_Foo"
    )
    ib_fs = extract_from_intended_behavior("use stringify like issue example")
    if issue_fs and neighbor_fs:
        assert contracts_conflict(issue_fs, neighbor_fs, ib_fs) or callee_jaccard(
            issue_fs, neighbor_fs
        ) < 0.3


def test_issue_aligns_with_neighbor_no_conflict():
    neighbor_src = "def _print_Foo(self, e):\n    return self._print(e)"
    neighbor_fs = extract_from_source(neighbor_src, "_print_Foo")
    issue = "```python\ndef _print_Foo(self, e):\n    return self._print(e)\n```"
    from app.knowledge.contract_features import extract_from_issue

    issue_fs = extract_from_issue(issue)
    ib_fs = extract_from_intended_behavior("delegate via self._print")
    if issue_fs and neighbor_fs:
        assert not contracts_conflict(issue_fs, neighbor_fs, ib_fs)
