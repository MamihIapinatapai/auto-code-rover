#!/usr/bin/env python3
"""Evaluate spec parser across probe instances; outputs metrics report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.infrastructure.shared_memory import SharedMemoryStore  # noqa: E402
from app.spec_parser.schema import StructuredSpecification  # noqa: E402

PROBE_GT = {
    "sympy__sympy-11400": {
        "prerequisite": ["Relational"],
        "co_fix": [],
        "layer": "delegate_chain",
    },
    "sympy__sympy-12454": {
        "prerequisite": [],
        "co_fix": ["hessenberg"],
        "layer": "dimension_clamp",
    },
    "sympy__sympy-12481": {
        "layer": "guard",
    },
    "sympy__sympy-11897": {
        "layer": "bracket_decision",
    },
    "sympy__sympy-12171": {
        "layer": "unknown",
    },
}


def score_instance(instance_id: str, spec: StructuredSpecification, probe_dir: Path) -> dict:
    gt = PROBE_GT.get(instance_id, {})
    metrics: dict = {"instance_id": instance_id, "json_valid": True}

    text_blob = spec.model_dump_json()
    if gt.get("prerequisite"):
        metrics["prerequisite_recall"] = all(
            p.lower() in text_blob.lower() for p in gt["prerequisite"]
        )
    if gt.get("co_fix"):
        co = " ".join(spec.fix_scope.co_fix_required).lower()
        metrics["co_fix_recall"] = all(c.lower() in co or c.lower() in text_blob.lower() for c in gt["co_fix"])

    if gt.get("layer"):
        metrics["layer_accuracy"] = spec.architecture_hint.layer == gt["layer"] or gt["layer"] in text_blob

    sc_path = probe_dir / instance_id / SharedMemoryStore.SEARCH_CONTEXT_FILENAME
    metrics["search_context_coverage"] = sc_path.is_file() and sc_path.stat().st_size > 50

    tr_path = probe_dir / instance_id / SharedMemoryStore.TARGET_RESOLUTION_FILENAME
    metrics["target_resolution_exists"] = False
    if tr_path.is_file():
        try:
            tr_data = json.loads(tr_path.read_text())
            candidates = tr_data.get("candidates") or []
            metrics["target_resolution_exists"] = bool(candidates)
        except json.JSONDecodeError:
            metrics["target_resolution_exists"] = False

    if spec.execution_evidence:
        metrics["calibration_passed"] = spec.execution_evidence.calibration_passed
        metrics["primary_failure_ac_id"] = spec.execution_evidence.primary_failure_ac_id

    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--task-list",
        type=Path,
        default=ROOT / "conf" / "lite300_tasks" / "sympy_five_probes.txt",
    )
    parser.add_argument(
        "--probe-dir",
        type=Path,
        default=ROOT / "experiment" / "spec_parser_probe",
    )
    parser.add_argument(
        "--mode",
        choices=["spec-only", "search-injection"],
        default="spec-only",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    instance_ids = [
        ln.strip()
        for ln in args.task_list.read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]

    report = {"mode": args.mode, "instances": []}
    for iid in instance_ids:
        swm_path = args.probe_dir / iid / SharedMemoryStore.FILENAME
        if not swm_path.is_file():
            report["instances"].append({"instance_id": iid, "error": "missing SWM"})
            continue
        swm = SharedMemoryStore.read(args.probe_dir / iid)
        assert swm is not None
        metrics = score_instance(iid, swm.structured_spec, args.probe_dir)
        report["instances"].append(metrics)

    out = args.output or args.probe_dir / "spec_parser_eval_report.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
