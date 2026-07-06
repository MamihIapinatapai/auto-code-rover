#!/usr/bin/env python3
"""Finish patch selection for applicable_patch dirs interrupted before success log.

Legacy L2 runs could exit patch selection early (run_task_in_subprocess did not wait
on the worker Future). This script runs select_patch only and writes the success line
to info.log so verify_l2_output.py passes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loguru import logger

from app import config, inference, log
from app.model import common
from app.model.register import register_all_models
from app.raw_tasks import RawSweTask

LOG_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level>"
    " | <level>{message}</level>"
)


def instance_id_from_task_dir(task_dir: Path) -> str:
    meta_path = task_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("task_id"):
            return str(meta["task_id"])
    name = task_dir.name
    for suffix in ("_20",):
        idx = name.find(suffix)
        if idx > 0:
            return name[:idx]
    return name.rsplit("_", 2)[0]


def needs_repair(task_dir: Path, instance_id: str) -> bool:
    info_log = task_dir / "info.log"
    if not info_log.is_file():
        return True
    text = info_log.read_text(encoding="utf-8", errors="replace")
    return f"Task {instance_id} completed successfully" not in text


def complete_task_dir(task_dir: Path, instance_id: str) -> bool:
    meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
    raw_task = RawSweTask(meta["task_id"], meta["setup_info"], meta["task_info"])
    task = raw_task.to_task()

    log_path = task_dir / "info.log"
    sink_id = logger.add(
        str(log_path),
        level="DEBUG",
        format=LOG_FORMAT,
        mode="a",
    )
    log.print_stdout = False
    try:
        logger.info("Starting patch selection (repair)")
        selected, details = inference.select_patch(task, task_dir)
        (task_dir / "selected_patch.json").write_text(
            json.dumps(details, indent=4),
            encoding="utf-8",
        )
        logger.info("Selected patch {}. Reason: {}", selected, details["reason"])
        log.log_and_always_print(f"Task {instance_id} completed successfully.")
        print(f"[ok] {instance_id}")
        return True
    except Exception as exc:
        print(f"[fail] {instance_id}: {exc}", file=sys.stderr)
        return False
    finally:
        logger.remove(sink_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Complete interrupted L2 patch selection under applicable_patch/"
    )
    parser.add_argument(
        "--expr-dir",
        type=Path,
        default=ROOT / "experiment" / "deepseek-lite-pilot",
        help="Experiment directory containing applicable_patch/",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config.enable_validation = False

    register_all_models()
    common.set_model(
        os.getenv(
            "ACR_PATCH_SELECT_MODEL",
            "litellm-generic-deepseek/deepseek-chat",
        )
    )

    applicable_dir = args.expr_dir.resolve() / "applicable_patch"
    if not applicable_dir.is_dir():
        print(f"Missing {applicable_dir}", file=sys.stderr)
        return 1

    task_dirs = sorted(p for p in applicable_dir.iterdir() if p.is_dir())
    if not task_dirs:
        print("No task directories under applicable_patch/", file=sys.stderr)
        return 1

    failed: list[str] = []
    skipped = 0
    repaired = 0
    for task_dir in task_dirs:
        instance_id = instance_id_from_task_dir(task_dir)
        if not needs_repair(task_dir, instance_id):
            skipped += 1
            continue
        if args.dry_run:
            print(f"[dry-run] would repair {instance_id}")
            continue
        if complete_task_dir(task_dir, instance_id):
            repaired += 1
        else:
            failed.append(instance_id)

    if args.dry_run:
        pending = len(task_dirs) - skipped
        print(f"Would repair {pending} task(s), skip {skipped}")
        return 0

    print(f"Repaired {repaired}, skipped {skipped}, failed {len(failed)}")
    if failed:
        print("Failed: " + ", ".join(failed), file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
