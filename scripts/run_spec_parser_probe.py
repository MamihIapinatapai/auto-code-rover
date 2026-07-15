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
from app.spec_parser.pipeline import (  # noqa: E402
    V2_PARSER_VERSION,
    V3_PARSER_VERSION,
    apply_spec_parser_version,
    configure_repo_enrichment,
)
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
    parser.add_argument(
        "--use-v3-prompts",
        action="store_true",
        default=False,
        help="Use v3.0 dual script prompts (BUG_FIX/FEATURE) and scaffold wrapping.",
    )
    parser.add_argument(
        "--spec-parser-version",
        choices=[V2_PARSER_VERSION, V3_PARSER_VERSION],
        default=None,
        help="Pipeline version: 3.0.0 disables P2 static analysis by default.",
    )
    parser.add_argument(
        "--no-repo-enrichment",
        action="store_true",
        help="Disable P2 repo_enrichment (static AST analysis).",
    )
    parser.add_argument(
        "--with-repo-enrichment",
        action="store_true",
        help="Force-enable P2 repo_enrichment (ablation vs v3 no-static).",
    )
    args = parser.parse_args()

    if os.environ.get("ACR_SYMPY_PIPELINE_V2", "").lower() in ("0", "false", "no"):
        config.enable_sympy_pipeline_v2 = False
    if os.environ.get("ACR_SPEC_PARSER_SCOPE_LLM", "").lower() in ("1", "true", "yes"):
        config.spec_parser_scope_llm = True
    if os.environ.get("ACR_SPEC_PARSER_USE_V3_PROMPTS", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        config.spec_parser_use_v3_prompts = True
    if os.environ.get("ACR_SPEC_PARSER_VERSION", "").strip():
        apply_spec_parser_version(os.environ["ACR_SPEC_PARSER_VERSION"].strip())
    if os.environ.get("ACR_SPEC_PARSER_NO_REPO_ENRICHMENT", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        args.no_repo_enrichment = True
    if args.spec_parser_scope_llm:
        config.spec_parser_scope_llm = True
    if args.use_v3_prompts:
        config.spec_parser_use_v3_prompts = True
    if args.spec_parser_version:
        apply_spec_parser_version(args.spec_parser_version)
    config.enable_spec_parser = True
    configure_repo_enrichment(
        stop_after=args.stop_after,
        no_repo_enrichment=args.no_repo_enrichment,
        with_repo_enrichment=args.with_repo_enrichment,
    )

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
    print(f"parser_version: {spec.parser_version}")
    print(f"repo_enrichment: {'on' if config.spec_parser_enable_repo_enrichment else 'off'}")
    print(f"repair_goals: {spec.repair_goals}")


if __name__ == "__main__":
    main()
