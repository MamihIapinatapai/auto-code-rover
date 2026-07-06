#!/usr/bin/env python3
"""Verify L2 agent output before L3 eval or Feishu upload (SERVER_REPLICATION_GUIDE §5.7)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def load_expected_ids(tasks_file: Path | None, expected: int | None) -> list[str] | None:
    if tasks_file is None:
        return None
    lines = [
        ln.strip()
        for ln in tasks_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if expected is not None and len(lines) != expected:
        print(
            f"WARNING: tasks file has {len(lines)} ids, --expected {expected}",
            file=sys.stderr,
        )
    return lines


def instance_id_from_task_dir(task_dir: Path) -> str:
    meta_path = task_dir / "meta.json"
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("task_id"):
            return str(meta["task_id"])
    name = task_dir.name
    for suffix in ("_20",):  # date suffix YYYY-MM-DD
        idx = name.find(suffix)
        if idx > 0:
            return name[:idx]
    return name.rsplit("_", 2)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify L2 predictions and applicable_patch artifacts.")
    parser.add_argument(
        "--expr-dir",
        type=Path,
        default=ROOT / "experiment" / "deepseek-lite-pilot",
        help="Experiment directory (default: experiment/deepseek-lite-pilot)",
    )
    parser.add_argument(
        "--expected",
        type=int,
        default=None,
        help="Expected task count (overrides predictions length check if set)",
    )
    parser.add_argument(
        "--tasks-file",
        type=Path,
        default=None,
        help="Optional task list file to cross-check instance ids",
    )
    args = parser.parse_args()

    expr_dir = args.expr_dir.resolve()
    predictions_path = expr_dir / "predictions_for_swebench.json"
    applicable_dir = expr_dir / "applicable_patch"
    no_patch_dir = expr_dir / "no_patch"

    all_ok = True

    if not predictions_path.is_file():
        all_ok &= check("predictions_for_swebench.json", False, f"missing {predictions_path}")
        return 1

    predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
    if isinstance(predictions, list):
        pred_ids = [p["instance_id"] for p in predictions]
    else:
        pred_ids = list(predictions.keys())

    expected_n = args.expected if args.expected is not None else len(pred_ids)
    all_ok &= check("predictions count", len(pred_ids) == expected_n, f"{len(pred_ids)}/{expected_n}")

    if not applicable_dir.is_dir():
        all_ok &= check("applicable_patch/", False, "missing")
        return 1

    task_dirs = sorted(p for p in applicable_dir.iterdir() if p.is_dir())
    all_ok &= check("applicable_patch count", len(task_dirs) == expected_n, f"{len(task_dirs)}/{expected_n}")

    no_patch_count = 0
    if no_patch_dir.is_dir():
        no_patch_count = sum(1 for p in no_patch_dir.iterdir() if p.is_dir())
    all_ok &= check("no_patch empty", no_patch_count == 0, f"{no_patch_count} dirs")

    missing_cost: list[str] = []
    missing_success_log: list[str] = []
    for task_dir in task_dirs:
        iid = instance_id_from_task_dir(task_dir)
        if not (task_dir / "cost.json").is_file():
            missing_cost.append(iid)
        info_log = task_dir / "info.log"
        if not info_log.is_file():
            missing_success_log.append(iid)
            continue
        if f"Task {iid} completed successfully" not in info_log.read_text(encoding="utf-8", errors="replace"):
            missing_success_log.append(iid)

    all_ok &= check(
        "cost.json per applicable task",
        not missing_cost,
        ", ".join(missing_cost) if missing_cost else f"{len(task_dirs)} ok",
    )
    all_ok &= check(
        "info.log completed successfully",
        not missing_success_log,
        ", ".join(missing_success_log) if missing_success_log else f"{len(task_dirs)} ok",
    )

    if args.tasks_file:
        task_ids = load_expected_ids(args.tasks_file.resolve(), args.expected)
        if task_ids is not None:
            missing_preds = sorted(set(task_ids) - set(pred_ids))
            extra_preds = sorted(set(pred_ids) - set(task_ids))
            all_ok &= check(
                "predictions match tasks file",
                not missing_preds and not extra_preds,
                f"missing={missing_preds or '-'} extra={extra_preds or '-'}",
            )

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
