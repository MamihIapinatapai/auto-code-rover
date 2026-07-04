#!/usr/bin/env python3
"""Run specification parser on a single SWE-bench instance (spec-only debug)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.model.register import register_all_models  # noqa: E402
from app.model.gpt import common  # noqa: E402
from app.raw_tasks import RawSweTask  # noqa: E402
from app.spec_parser.agent import SpecParsingAgent  # noqa: E402
from app.task import SweTask  # noqa: E402


def load_issue_from_tasks_map(instance_id: str, tasks_map: Path) -> tuple[dict, str]:
    data = json.loads(tasks_map.read_text())
    entry = data.get(instance_id)
    if not entry:
        raise SystemExit(f"Instance {instance_id} not in {tasks_map}")
    return entry, entry.get("problem_statement", "")


def build_task(instance_id: str, setup_map: Path, tasks_map: Path) -> SweTask:
    setup_data = json.loads(setup_map.read_text())
    tasks_data = json.loads(tasks_map.read_text())
    if instance_id not in tasks_data:
        raise SystemExit(f"Instance {instance_id} not in {tasks_map}")
    if instance_id not in setup_data:
        raise SystemExit(f"Instance {instance_id} not in {setup_map}")
    raw = RawSweTask(instance_id, setup_data[instance_id], tasks_data[instance_id])
    return raw.to_task()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run spec parser on one probe instance")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "experiment" / "spec_parser_probe",
    )
    parser.add_argument(
        "--stop-after",
        choices=["extract", "enrich", "fusion", "calibration", "full"],
        default="full",
    )
    parser.add_argument("--no-llm-script", action="store_true")
    parser.add_argument("--setup-map", type=Path, default=ROOT / "setup_map.json")
    parser.add_argument("--tasks-map", type=Path, default=ROOT / "tasks_map.json")
    parser.add_argument("--model", default="gpt-3.5-turbo-0125")
    parser.add_argument(
        "--spec-parser-scope-llm",
        action="store_true",
        default=False,
        help="Enable optional ScopePlan LLM for P2 (default: deterministic scope).",
    )
    args = parser.parse_args()

    if os.environ.get("ACR_SYMPY_PIPELINE_V2", "").lower() in ("0", "false", "no"):
        config.enable_sympy_pipeline_v2 = False
    if os.environ.get("ACR_SPEC_PARSER_SCOPE_LLM", "").lower() in ("1", "true", "yes"):
        config.spec_parser_scope_llm = True
    if args.spec_parser_scope_llm:
        config.spec_parser_scope_llm = True
    config.enable_spec_parser = True
    config.spec_parser_enable_repo_enrichment = args.stop_after not in ("extract",)

    register_all_models()
    common.set_model(args.model)

    task = build_task(args.instance_id, args.setup_map, args.tasks_map)
    out = args.output_dir / args.instance_id
    out.mkdir(parents=True, exist_ok=True)

    _, issue_text = load_issue_from_tasks_map(args.instance_id, args.tasks_map)
    agent = SpecParsingAgent(task, str(out))
    spec = agent.run(
        issue_text,
        stop_after=args.stop_after,
        use_llm_for_script=not args.no_llm_script,
    )
    print(f"Wrote artifacts to {out}")
    print(f"repair_goals: {spec.repair_goals}")


if __name__ == "__main__":
    main()
