"""Tests for repo enrichment AST rules."""

from pathlib import Path

from app.spec_parser.rules import printing_rules
from app.spec_parser.visitors.return_shape import ForLoopVisitor, index_class_methods


def test_for_loop_visitor_detects_unclamped_j():
    source = """
class M:
    def is_upper(self):
        for i in range(self.rows):
            for j in range(i):
                if self[i, j]:
                    return False
        return True
"""
    tree = __import__("ast").parse(source)
    for node in __import__("ast").walk(tree):
        if isinstance(node, __import__("ast").FunctionDef) and node.name == "is_upper":
            vis = ForLoopVisitor()
            vis.visit(node)
            assert any(l.is_unclamped_j_loop for l in vis.loops)


def test_index_class_methods():
    source = "class C:\n    def foo(self): pass\n"
    methods = index_class_methods(source, "C")
    assert "foo" in methods


def test_printing_rules_missing_handlers_on_empty_project(tmp_path):
    issue = "ccode(sinc(x)) and ccode(Ne(x,0))"
    (tmp_path / "sympy").mkdir()
    (tmp_path / "sympy" / "printing").mkdir(parents=True)
    ccode = tmp_path / "sympy" / "printing" / "ccode.py"
    ccode.write_text(
        "class CCodePrinter:\n    def _print_Piecewise(self, expr): pass\n"
    )

    class FakeTask:
        project_path = str(tmp_path)

    enrichment = printing_rules.enrich(FakeTask(), issue, None)
    assert "_print_sinc" in enrichment.missing_handlers or "_print_Relational" in enrichment.missing_handlers
