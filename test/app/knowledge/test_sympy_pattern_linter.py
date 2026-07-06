"""Tests for sympy_pattern_linter / DiffRegressionEngine."""

from unittest.mock import patch

from app.knowledge.sympy_pattern_linter import DiffRegressionEngine


def test_no_artifact_warn_only():
    with patch("app.knowledge.sympy_pattern_linter.config") as mock_cfg:
        mock_cfg.enable_sympy_pipeline_v2 = True
        engine = DiffRegressionEngine()
        findings = engine.check("/nonexistent.diff", "/tmp", None, [], prev_diff_path=None)
    assert any(f.rule_id == "PL_ARTIFACT_MISSING" for f in findings)
    assert not any(f.severity == "block" for f in findings)
