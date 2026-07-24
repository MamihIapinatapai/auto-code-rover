"""Phase 0 V1–V6 / §14 mechanical gates for Spec Parser v3.4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import config
from app.spec_parser.artifact_store import write_artifact_consistency_report
from app.spec_parser.behavior_contract import validate_contract
from app.spec_parser.behavior_skeleton import render_s1_script
from app.spec_parser.calibration_gate import (
    classify_gate_triage,
    extract_json_blob,
    feature_signal_ok,
)
from app.spec_parser.dual_state_lite import check_dsl_rules
from app.spec_parser.pipeline import apply_spec_parser_version
from app.spec_parser.recipe_loader import load_recipe_cards, recipe_compliance
from app.spec_parser.schema import DraftMetrics, TaskType
from app.spec_parser.script_contract_align import run_scc_machine
from app.spec_parser.draft_picker import score_draft


@pytest.fixture(autouse=True)
def _v34_config():
    apply_spec_parser_version("3.4.0")
    yield


def _good_adaptix_item(issue_quote: str = "Use name_mapping in Retort recipe"):
    return {
        "must_id": "M1-name-mapping",
        "issue_quote": issue_quote,
        "layer": "lib",
        "call_graph": ["Retort", "name_mapping", "load"],
        "inputs": {"data": {"user_name": "a"}},
        "oracle_kind": "field_path",
        "expect": {
            "oracle_kind": "field_path",
            "field_path": "name",
            "value": "a",
            "compare": "eq",
        },
        "fail_mode": "attr_error",
        "recipe_id": "adaptix.name_mapping",
        "expect_confidence": "high",
        "tier": "S1",
    }


def test_v1_recipe_rejects_provider_direct_call():
    cards = load_recipe_cards()
    assert "adaptix.name_mapping" in cards
    bad = "mapping = name_mapping(...)(Model)\nresult = mapping.load({})"
    good = "retort = Retort(recipe=[name_mapping(aliases={})])\nloader = retort.get_loader(Model)"
    assert recipe_compliance(good, "adaptix.name_mapping")
    # forbidden pattern Retort(name_mapping= or name_mapping(...)(
    assert not recipe_compliance(
        "Retort(name_mapping=x)", "adaptix.name_mapping"
    )


def test_v2_dsl01_async_loop():
    script = "import asyncio\nasyncio.run_coroutine_threadsafe(coro(), loop)\n"
    r = check_dsl_rules(script)
    assert not r["passed"]
    assert any(b["rule_id"] == "DSL-01" for b in r["blocking"])
    ok = "import asyncio\nasyncio.run(main())\n"
    assert check_dsl_rules(ok)["passed"]


def test_v4_bc05_existence_call_graph():
    issue = "Must expose feature_api for users"
    contract = {
        "items": [
            {
                "must_id": "M1",
                "issue_quote": "Must expose feature_api",
                "layer": "lib",
                "call_graph": ["hasattr"],
                "inputs": {},
                "oracle_kind": "equality",
                "expect": {"oracle_kind": "equality", "value": True},
                "fail_mode": "assert",
                "expect_confidence": "high",
            }
        ]
    }
    r = validate_contract(contract, issue_text=issue)
    assert not r["passed"]
    assert any(b["rule_id"] == "BC-05" for b in r["blocking"])


def test_v4_bc08_recipe_forbidden_on_graph():
    issue = "Use name_mapping in Retort recipe"
    item = _good_adaptix_item(issue)
    item["call_graph"] = ["name_mapping", "load"]  # missing Retort/recipe
    # also hit forbidden style in joined graph string
    item["call_graph"] = ["Retort(name_mapping=", "load"]
    r = validate_contract(
        {"items": [item]}, issue_text=issue, recipe_cards=load_recipe_cards()
    )
    assert not r["passed"]
    assert any(b["rule_id"] == "BC-08" for b in r["blocking"])


def test_v4_bc09b_cattrs_pattern():
    issue = "When nested required fields are missing, value must be None"
    contract = {
        "items": [
            {
                "must_id": "M1",
                "issue_quote": "required fields are missing, value must be None",
                "layer": "lib",
                "call_graph": ["structure", "recover"],
                "inputs": {},
                "oracle_kind": "equality",
                "expect": {"oracle_kind": "equality", "value": {"a": 1}},
                "fail_mode": "assert",
                "expect_confidence": "high",
            }
        ]
    }
    r = validate_contract(contract, issue_text=issue)
    assert not r["passed"]
    assert any(b["rule_id"] == "BC-09b" for b in r["blocking"])
    # good: field_path null
    contract["items"][0]["oracle_kind"] = "field_path"
    contract["items"][0]["expect"] = {
        "oracle_kind": "field_path",
        "field_path": "value",
        "value": None,
    }
    r2 = validate_contract(contract, issue_text=issue)
    assert r2["passed"] or not any(b["rule_id"] == "BC-09b" for b in r2["blocking"])


def test_v4_good_row_passes():
    issue = "Use name_mapping in Retort recipe to load aliases"
    contract = {"items": [_good_adaptix_item("Use name_mapping in Retort recipe")]}
    r = validate_contract(
        contract, issue_text=issue, recipe_cards=load_recipe_cards()
    )
    assert r["passed"], r


def test_v6_scc03_missing_literal():
    issue = "Use name_mapping in Retort recipe"
    contract = {"items": [_good_adaptix_item(issue)]}
    mid = "M1_name_mapping"  # sanitize of M1-name-mapping
    script = (
        f"# --- AC-{mid} ---\n"
        f"def test_ac_{mid}():\n"
        "    Retort\n    name_mapping\n    load\n"
        "    result = None\n"
        "    assert result == 'WRONG'\n"
        "    raise AssertionError('NOT_IMPLEMENTED')\n"
    )
    scc = run_scc_machine(contract, script, issue_text=issue)
    assert scc["blocking"]
    assert any(f["rule_id"] == "SCC-03" for f in scc["findings"])


def test_v6_scc08_recipe_source():
    issue = "Use name_mapping in Retort recipe"
    contract = {"items": [_good_adaptix_item(issue)]}
    script = render_s1_script(contract, recipe_cards=load_recipe_cards())
    if hasattr(script, "script"):
        script = script.script or ""
    # corrupt recipe patterns out
    bad = script.replace("Retort", "Provider").replace("recipe", "xx")
    # Ensure call_graph symbols still present somehow
    scc = run_scc_machine(contract, bad, issue_text=issue)
    # may hit SCC-02 or SCC-08
    assert scc["blocking"]


def test_v6_scc09_private_import():
    issue = "public API only"
    contract = {
        "items": [
            {
                "must_id": "M1",
                "issue_quote": "public API only",
                "layer": "lib",
                "call_graph": ["load"],
                "inputs": {},
                "oracle_kind": "equality",
                "expect": {"oracle_kind": "equality", "value": 1},
                "fail_mode": "assert",
                "expect_confidence": "high",
            }
        ]
    }
    script = (
        "# --- AC-M1 ---\n"
        "def test_ac_M1():\n"
        "    from pkg._internal import X\n"
        "    load\n"
        "    result = 1\n"
        "    assert result == 1\n"
        "    raise AssertionError('NOT_IMPLEMENTED')\n"
    )
    scc = run_scc_machine(contract, script, issue_text=issue)
    assert any(f["rule_id"] == "SCC-09" for f in scc["findings"])


def test_gat_m1_triage():
    assert (
        classify_gate_triage(
            TaskType.FEATURE,
            "ModuleNotFoundError: No module named 'pandas'",
            "import pandas",
            issue_text="add rolling window",
        )
        == "missing_third_party"
    )
    assert (
        classify_gate_triage(
            TaskType.FEATURE,
            "ModuleNotFoundError: No module named 'sqlfmt.ddl'",
            "import sqlfmt.ddl",
            issue_text="sqlfmt.ddl formatting for create table",
        )
        == "missing_feature_module"
    )
    assert feature_signal_ok("missing_feature_module")
    assert not feature_signal_ok("feature_fail")


def test_bandit_extract_json_blob():
    stdout = "noise\n{\"results\": []}\nmore"
    assert extract_json_blob(stdout) == '{"results": []}'
    assert extract_json_blob("not json") is None


def test_art_m1(tmp_path: Path):
    script = tmp_path / "test_feature.py"
    script.write_text("def test_ac_M1():\n    pass\n", encoding="utf-8")
    report = write_artifact_consistency_report(
        tmp_path, final_action="no_script", selected_draft_id=""
    )
    assert not script.exists()
    assert report["artifact_consistent"]
    assert report["disk_script_present"] is False


def test_draft_score_v34():
    config.spec_parser_draft_score_version = "v34"
    m = DraftMetrics(
        draft_id="r1",
        round_no=1,
        concrete_expect_ac_count=1,
        recipe_compliance_bonus=1,
        scc_m_pass=True,
        behavioral_ac_count=1,
        feature_calib_ok=True,
        contract_path_s1=True,
    )
    s = score_draft(m)
    # 12+15+10+6+20+8 = 71
    assert s == 71.0


def test_dsl03_handler_without_path():
    script = "class MonitorWebHandler: pass\nclient = MonitorWebHandler()\n"
    r = check_dsl_rules(script)
    assert any(b["rule_id"] == "DSL-03" for b in r["blocking"])
