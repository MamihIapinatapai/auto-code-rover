#!/usr/bin/env python3
"""Regenerate report/instances/*.json for Lite300 repos without re-running L3 eval."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "pengxm-acr-replicate"
SWE_TASKS = "/opt/SWE-bench/data/swe-bench.json"
DOCKER_DIR = "/workspace/acr/SWE-bench-docker"


def load_predictions(repo: str, sync_dir: Path, instance_ids: set[str]) -> list[dict]:
    search_dirs = [
        sync_dir,
        ROOT / "experiment" / "deepseek-lite-300" / "repos" / repo,
    ]
    collected: dict[str, dict] = {}

    for base in search_dirs:
        if not base.is_dir():
            continue
        for iid in instance_ids:
            if iid in collected:
                continue
            single = base / f"predictions_{iid}.json"
            if single.is_file():
                item = json.loads(single.read_text(encoding="utf-8"))
                if isinstance(item, list):
                    item = item[0]
                collected[iid] = item

        for name in ("predictions_for_swebench.sanitized.json", "predictions_for_swebench.json"):
            path = base / name
            if not path.is_file():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else list(data.values())
            for pred in items:
                iid = pred["instance_id"]
                if iid in instance_ids and iid not in collected:
                    collected[iid] = pred

    if not collected:
        raise FileNotFoundError(f"No predictions for {instance_ids} under {search_dirs}")
    return [collected[iid] for iid in sorted(collected)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate Lite300 report/instances JSON.")
    parser.add_argument("--repo", required=True, help="Lite300 repo key, e.g. django")
    parser.add_argument(
        "--instance-id",
        action="append",
        default=[],
        metavar="ID",
        help="Only these instances (repeatable). Default: all with eval logs.",
    )
    parser.add_argument(
        "--sync-dir",
        type=Path,
        default=None,
        help="Override sync dir (default: lite300_output/repos/<repo>)",
    )
    parser.add_argument(
        "--container",
        default=CONTAINER,
        help=f"Docker container name (default: {CONTAINER})",
    )
    args = parser.parse_args()

    sync_dir = args.sync_dir or (ROOT / "lite300_output" / "repos" / args.repo)
    sync_dir = sync_dir.resolve()
    if not sync_dir.is_dir():
        print(f"Missing sync dir: {sync_dir}", file=sys.stderr)
        return 1

    eval_logs = sync_dir / "eval_logs"
    report_dir = sync_dir / "report"
    if not eval_logs.is_dir():
        print(f"Missing eval_logs: {eval_logs}", file=sys.stderr)
        return 1

    if args.instance_id:
        target_ids = set(args.instance_id)
    else:
        target_ids = {
            p.name.split(".", 1)[0]
            for p in eval_logs.glob("*.eval.log")
        }

    preds = load_predictions(args.repo, sync_dir, target_ids)
    found_ids = {p["instance_id"] for p in preds}
    missing = sorted(target_ids - found_ids)
    if missing:
        print(f"WARNING: no prediction for: {', '.join(missing)}", file=sys.stderr)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(preds, tmp, indent=2)
        tmp_path = Path(tmp.name)

    container_preds = f"/tmp/lite300_regen_preds_{args.repo}.json"
    container_report = f"/workspace/acr/{sync_dir.relative_to(ROOT)}/report"

    subprocess.run(
        ["docker", "cp", str(tmp_path), f"{args.container}:{container_preds}"],
        check=True,
    )
    tmp_path.unlink(missing_ok=True)

    rel_sync = sync_dir.relative_to(ROOT)
    container_logs = f"/workspace/acr/{rel_sync}/eval_logs"

    cmd = (
        f"source /root/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate auto-code-rover && "
        f"cd {DOCKER_DIR} && python generate_report.py "
        f"--predictions_path {container_preds} "
        f"--log_dir {container_logs} "
        f"--swe_bench_tasks {SWE_TASKS} "
        f"--output_dir {container_report}"
    )
    print(f"Running in container {args.container}: {cmd}")
    proc = subprocess.run(
        ["docker", "exec", args.container, "bash", "-lc", cmd],
        text=True,
    )
    if proc.returncode != 0:
        return proc.returncode

    instances_dir = report_dir / "instances"
    written = sorted(p.name for p in instances_dir.glob("*.json")) if instances_dir.is_dir() else []
    print(f"Instance reports under {instances_dir}: {len(written)}")
    for name in written:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
