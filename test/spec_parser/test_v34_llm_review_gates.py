"""Unit tests for v3.4 table LLM review + SCC-L gates."""

from __future__ import annotations

from app import config
from app.spec_parser.contract_llm_review import (
    sanitize_review_result,
    should_run_table_llm_review,
)
from app.spec_parser.script_contract_align import should_run_scc_llm


def test_table_llm_disabled_by_default():
    config.spec_parser_enable_contract_llm_review = False
    ok, reasons = should_run_table_llm_review(
        {"items": [{"layer": "web", "expect_confidence": "high"}]},
        issue_text="must must must",
        task_id="x",
    )
    assert ok is False


def test_table_llm_high_risk_web():
    config.spec_parser_enable_contract_llm_review = True
    config.spec_parser_contract_llm_review_mode = "high_risk_only"
    ok, reasons = should_run_table_llm_review(
        {"items": [{"layer": "web", "expect_confidence": "high", "call_graph": ["a"]}]},
        issue_text="feature",
        task_id="t",
    )
    assert ok is True
    assert any("web" in r for r in reasons)


def test_sanitize_illegal_verdict_not_pass():
    out = sanitize_review_result(
        {"verdict": "totally_invalid", "item_findings": []},
        issue_text="hello",
        contract={"items": []},
    )
    assert out["verdict"] != "pass" or out["verdict"] == "warning"
    assert out["verdict"] in {
        "pass",
        "warning",
        "revise_expect",
        "reject_false_fail",
        "reject_off_must",
    }
    assert out["verdict"] == "warning"


def test_sanitize_reject_without_evidence_downgrades():
    out = sanitize_review_result(
        {
            "verdict": "reject_false_fail",
            "blocking": True,
            "item_findings": [
                {
                    "must_id": "M1",
                    "issue": "false_fail",
                    "severity": "blocking",
                    "claim": "bad",
                    "evidence_chain": [],
                }
            ],
        },
        issue_text="value should be None",
        contract={"items": [{"must_id": "M1", "issue_quote": "value should be None"}]},
    )
    # empty chain → insufficient_evidence → cannot keep reject
    assert out["verdict"] in {"warning", "pass"}
    assert out["blocking"] is False


def test_scc_l_disabled():
    config.spec_parser_enable_script_contract_llm = False
    ok, _ = should_run_scc_llm(
        {"items": [{"layer": "async"}]},
        {"scc_m_pass": True, "findings": []},
        issue_text="x",
        task_id="t",
    )
    assert ok is False


def test_scc_l_high_risk_when_enabled():
    config.spec_parser_enable_script_contract_llm = True
    config.spec_parser_script_contract_llm_mode = "high_risk_only"
    ok, reasons = should_run_scc_llm(
        {"items": [{"layer": "async", "expect_confidence": "high"}]},
        {"scc_m_pass": True, "findings": []},
        issue_text="x",
        task_id="t",
    )
    assert ok is True
    assert reasons
