"""Evidence-based tests for console_scripts parsing."""

from pathlib import Path

from app.spec_parser.entrypoint_meta import collect_entrypoint_meta, parse_pyproject_scripts


def test_parse_pyproject_scripts(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
[project.scripts]
demo-cli = "pkg.cli:main"
other = "pkg.other:run"
"""
    )
    eps = parse_pyproject_scripts(tmp_path)
    names = {e.name for e in eps}
    assert "demo-cli" in names
    assert any(e.target == "pkg.cli:main" for e in eps)


def test_collect_merges_without_dup(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ncli = "a.b:main"\n'
    )
    (tmp_path / "setup.cfg").write_text(
        "[options.entry_points]\nconsole_scripts =\n    cli = a.b:main\n"
    )
    eps = collect_entrypoint_meta(tmp_path)
    assert len([e for e in eps if e.name == "cli"]) == 1
