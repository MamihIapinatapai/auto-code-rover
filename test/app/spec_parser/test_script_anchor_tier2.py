"""Tier2 inspect tests with local package import."""

from pathlib import Path

from app.spec_parser.schema import AnchorSymbol, ScriptAnchor
from app.spec_parser.script_anchor_inspect import enrich_tier2, should_run_tier2


def test_should_run_tier2_gate():
    from app.spec_parser.pipeline import apply_spec_parser_version

    apply_spec_parser_version("3.3.1")
    anchor = ScriptAnchor(symbols=[AnchorSymbol(name="X")], tier1_ok=True)
    assert should_run_tier2(anchor, True)
    assert not should_run_tier2(anchor, False)
    assert not should_run_tier2(ScriptAnchor(), True)
    apply_spec_parser_version("3.3.0")  # restore


def test_enrich_tier2_runtime_signature(tmp_path: Path):
    pkg = tmp_path / "demo_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "api.py").write_text(
        "class Client:\n"
        "    def __init__(self, *, timeout=5):\n"
        "        self.timeout = timeout\n"
    )
    anchor = ScriptAnchor(
        package_roots=["demo_pkg"],
        symbols=[
            AnchorSymbol(
                name="Client",
                kind="class",
                rel_path="demo_pkg/api.py",
                signature_ast="(self)",
                confidence=0.85,
            )
        ],
        tier1_ok=True,
    )
    out = enrich_tier2(anchor, project_path=str(tmp_path))
    assert out.tier2_ok, out.tier2_skipped_reason
    assert "timeout" in (out.symbols[0].signature_runtime or "")
