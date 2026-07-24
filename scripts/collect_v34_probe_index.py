#!/usr/bin/env python3
"""Collect v3.4 probe artifacts into a machine-readable index for audit writing."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(
    "/datadisk/pengxm/acr_outputs/deepswe_spec_parser/deepswe-spec-parser-python-v3.4-probes"
)
TASKS = [
    "httpx-multipart-response-parsing",
    "httpx-streaming-json-iteration",
    "cattrs-partial-structuring-recovery",
    "aiomonitor-task-snapshots-diff",
    "sqlite-utils-safe-import-checkpoints",
    "python-statemachine-state-data-scoping",
    "gql-incremental-graphql-delivery",
    "igel-persist-feature-schema",
    "dateutil-rfc5545-timezone-interop",
    "sqlfmt-create-table-ddl-formatting",
    "psd-tools-blend-range-api",
    "adaptix-name-mapping-aliases",
    "bandit-structured-nosec-directives",
    "mashumaro-flattened-dataclass-fields",
    "narwhals-rolling-window-suite",
]


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def summarize_task(task_id: str) -> dict:
    d = ROOT / task_id
    trace = load_json(d / "script_decision_trace.json") or {}
    evidence = load_json(d / "execution_evidence.json") or {}
    art = load_json(d / "artifact_consistency.json") or {}
    contract = load_json(d / "behavior_contract.json")
    scc = load_json(d / "scc_report.json")
    nodes = trace.get("nodes") or []
    contract_path = any(n.get("decision") == "contract_path" for n in nodes) or bool(
        contract
    )
    script_path = d / "test_feature.py"
    if not script_path.exists():
        script_path = d / "reproduce_issue.py"
    script_head = ""
    if script_path.exists():
        script_head = script_path.read_text(encoding="utf-8", errors="replace")[:1500]
    return {
        "task_id": task_id,
        "exists": d.exists(),
        "final_action": trace.get("final_action"),
        "selected_draft_id": trace.get("selected_draft_id"),
        "contract_path": contract_path,
        "has_contract": contract is not None,
        "contract_items": len((contract or {}).get("items") or []) if contract else 0,
        "degraded": bool((contract or {}).get("degraded")) if contract else False,
        "scc_m_pass": (scc or {}).get("scc_m_pass"),
        "calib_error": evidence.get("calibration_error"),
        "exit_code": evidence.get("overall_exit_code"),
        "artifact": art,
        "node_summary": [
            f"{n.get('node_id')}:{n.get('decision')}" for n in nodes[-12:]
        ],
        "script_present": script_path.exists(),
        "script_head": script_head,
        "error": (d / "error.txt").read_text(encoding="utf-8")[:500]
        if (d / "error.txt").exists()
        else "",
    }


def main():
    rows = [summarize_task(t) for t in TASKS]
    out = ROOT / "_probe_index.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out} ({sum(1 for r in rows if r['exists'])}/15 present)")


if __name__ == "__main__":
    main()
