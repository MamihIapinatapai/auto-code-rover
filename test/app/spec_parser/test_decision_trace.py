"""Tests for v3.3 decision-trace recorder and early-stop."""

from pathlib import Path

from app.spec_parser.decision_trace import DecisionTraceRecorder, should_early_stop


def test_recorder_persists_json(tmp_path: Path):
    rec = DecisionTraceRecorder(
        task_id="t1",
        parser_version="3.3.0",
        output_dir=tmp_path,
        enabled=True,
    )
    rec.record(
        node_id="D_gate_classify",
        round_no=1,
        options=["env_failure", "pass"],
        decision="env_failure",
        reason="yaml missing",
        policy_id="gate_env_v33",
        action="calib_fail",
    )
    rec.set_final(final_action="regen")
    path = tmp_path / "script_decision_trace.json"
    assert path.is_file()
    text = path.read_text()
    assert "D_gate_classify" in text
    assert "env_failure" in text


def test_early_stop_stub_rounds():
    history = [
        {
            "blocking_rules": ["L12-STUB-AC"],
            "behavioral_ac_count": 0,
        },
        {
            "blocking_rules": ["L12-STUB-AC"],
            "behavioral_ac_count": 0,
        },
    ]
    assert should_early_stop(history, stub_rounds=2)
    history[1]["behavioral_ac_count"] = 2
    assert not should_early_stop(history, stub_rounds=2)
