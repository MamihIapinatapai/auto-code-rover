"""Tests for v3.3 coverage layer heuristics."""

from app.spec_parser.coverage_heuristics import check_layer_mismatch


def test_wrong_layer_cli_warning():
    script = """
# --- AC-007: CLI snapshot save ---
from aiomonitor import Monitor
assert Monitor().capture_snapshot() == 1
"""
    warnings = check_layer_mismatch(script, ["AC-007"])
    codes = {w["code"] for w in warnings}
    assert "WRONG_LAYER_CLI" in codes


def test_cli_ok_with_clirunner():
    script = """
# --- AC-007: CLI snapshot ---
from click.testing import CliRunner
runner = CliRunner()
result = runner.invoke(cli, ["snapshot", "save"])
assert result.exit_code == 0
"""
    warnings = check_layer_mismatch(script, ["AC-007"])
    assert not any(w["code"] == "WRONG_LAYER_CLI" for w in warnings)
