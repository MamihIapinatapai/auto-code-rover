#!/usr/bin/env python3
"""Collect v3.5 probe artifacts into a machine-readable index for audit writing."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(
    "/datadisk/pengxm/acr_outputs/deepswe_spec_parser/deepswe-spec-parser-python-v3.5-probes"
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

_STUB_RE = re.compile(r"None\s*#\s*invoke|NOT_IMPLEMENTED", re.I)


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
    usage = load_json(d / "usage_snippets.json")
    render = load_json(d / "render_result.json")
    eg = load_json(d / "failure_semantics.json")
    scc = load_json(d / "scc_report.json")
    nodes = trace.get("nodes") or []
    path_hint = ""
    for n in nodes:
        dec = str(n.get("decision") or "")
        if "contract" in dec or dec in {"free_gen", "contract_path", "contract_only"}:
            path_hint = dec
    script_path = d / "test_feature.py"
    if not script_path.exists():
        script_path = d / "reproduce_issue.py"
    script_text = ""
    if script_path.exists():
        script_text = script_path.read_text(encoding="utf-8", errors="replace")
    stub_hits = len(_STUB_RE.findall(script_text)) if script_text else 0
    return {
        "task_id": task_id,
        "exists": d.exists(),
        "final_action": trace.get("final_action") or art.get("final_action"),
        "selected_draft_id": trace.get("selected_draft_id"),
        "path_hint": path_hint,
        "has_contract": contract is not None,
        "contract_items": len((contract or {}).get("items") or []) if contract else 0,
        "degraded": bool((contract or {}).get("degraded")) if contract else False,
        "usage_snippets": len((usage or {}).get("snippets") or []) if usage else 0,
        "render_ok": (render or {}).get("ok") if render else None,
        "render_reason": (render or {}).get("reason_code") if render else None,
        "eg_blocking": (eg or {}).get("blocking") if eg else None,
        "scc_m_pass": (scc or {}).get("scc_m_pass"),
        "calib_error": evidence.get("calibration_error"),
        "calibration_passed": evidence.get("calibration_passed"),
        "exit_code": evidence.get("overall_exit_code"),
        "primary_failure": evidence.get("primary_failure"),
        "artifact": art,
        "node_summary": [
            f"{n.get('node_id')}:{n.get('decision')}" for n in nodes[-16:]
        ],
        "script_present": script_path.exists(),
        "script_bytes": len(script_text.encode("utf-8")) if script_text else 0,
        "stub_hits": stub_hits,
        "script_head": script_text[:2000],
        "error": (d / "error.txt").read_text(encoding="utf-8")[:500]
        if (d / "error.txt").exists()
        else "",
    }


def main():
    rows = [summarize_task(t) for t in TASKS]
    out = ROOT / "_probe_index.json"
    ROOT.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    present = sum(1 for r in rows if r["exists"])
    scripts = sum(1 for r in rows if r["script_present"])
    stubs = sum(1 for r in rows if r["stub_hits"] > 0)
    print(f"wrote {out} present={present}/15 scripts={scripts} stub_scripts={stubs}")


if __name__ == "__main__":
    main()
