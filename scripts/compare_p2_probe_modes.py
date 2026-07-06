#!/usr/bin/env python3
"""Compare deterministic P2 vs ScopePlan LLM probe outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def summarize_instance(instance_id: str, det_dir: Path, scope_dir: Path) -> dict:
    row: dict = {"instance_id": instance_id}

    for label, base in (("det", det_dir), ("scope_llm", scope_dir)):
        inst = base / instance_id
        swm = _load_json(inst / "shared_working_memory.json")
        tr = _load_json(inst / "target_resolution.json")
        ee = _load_json(inst / "execution_evidence.json")
        sc_path = inst / "search_context.txt"

        sub: dict = {"artifact_dir": str(inst)}
        if tr:
            sp = tr.get("scope_plan") or {}
            scope = tr.get("analysis_scope") or {}
            sub["scope_plan_used_llm"] = sp.get("used_llm", False)
            sub["scope_plan_validated"] = sp.get("validated", False)
            sub["scope_plan_fallback"] = sp.get("fallback", False)
            sub["analysis_scope_files"] = scope.get("files", [])[:5]
            sub["analysis_scope_visitors"] = scope.get("visitors", [])
            sub["candidate_count"] = len(tr.get("candidates") or [])
        if ee:
            sub["calibration_passed"] = ee.get("calibration_passed")
            sub["execution_mode"] = ee.get("execution_mode", "holistic")
        if swm:
            spec = swm.get("structured_spec") or {}
            sub["parser_version"] = spec.get("parser_version")
            sub["repair_goals_count"] = len(spec.get("repair_goals") or [])
            rs = spec.get("repro_script") or {}
            sub["repro_calibration_passed"] = rs.get("calibration_passed")
            sub["calibration_round"] = rs.get("calibration_round")
        sub["search_context_exists"] = sc_path.is_file()
        sub["search_context_bytes"] = sc_path.stat().st_size if sc_path.is_file() else 0
        row[label] = sub

    det_files = set(row.get("det", {}).get("analysis_scope_files") or [])
    scope_files = set(row.get("scope_llm", {}).get("analysis_scope_files") or [])
    row["scope_files_diff"] = {
        "only_det": sorted(det_files - scope_files),
        "only_scope_llm": sorted(scope_files - det_files),
        "same": det_files == scope_files,
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--det-dir", type=Path, required=True)
    parser.add_argument("--scope-dir", type=Path, required=True)
    parser.add_argument("--task-list", type=Path, default=ROOT / "conf/lite300_tasks/sympy_five_probes.txt")
    parser.add_argument("--output", type=Path, default=ROOT / "spec_parser_probe_p2_compare_report.json")
    args = parser.parse_args()

    instance_ids = [
        ln.strip()
        for ln in args.task_list.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    report = {
        "modes": {
            "deterministic": str(args.det_dir),
            "scope_llm": str(args.scope_dir),
        },
        "instances": [summarize_instance(iid, args.det_dir, args.scope_dir) for iid in instance_ids],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
