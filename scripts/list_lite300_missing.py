#!/usr/bin/env python3
"""List instance_ids missing from predictions or stuck in no_patch/unparsed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def load_task_ids(tasks_file: Path) -> list[str]:
    return [
        ln.strip()
        for ln in tasks_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def bucket_ids(expr_dir: Path, bucket: str) -> set[str]:
    d = expr_dir / bucket
    if not d.is_dir():
        return set()
    return {
        instance_id_from_task_dir(p)
        for p in d.iterdir()
        if p.is_dir()
    }


def pred_ids(expr_dir: Path) -> set[str]:
    path = expr_dir / "predictions_for_swebench.json"
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(p["instance_id"]) for p in data}
    return {str(k) for k in data}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write missing ids (one per line) to this file",
    )
    parser.add_argument(
        "--include-failed-buckets",
        action="store_true",
        help="Also treat no_patch and raw_patch_but_unparsed as needing rerun",
    )
    args = parser.parse_args()

    tasks_file = args.base / "conf" / "lite300_tasks" / f"{args.repo}.txt"
    expr_dir = args.base / "experiment" / "deepseek-lite-300" / "repos" / args.repo

    expected = load_task_ids(tasks_file)
    have_pred = pred_ids(expr_dir)
    missing = sorted(set(expected) - have_pred)

    if args.include_failed_buckets:
        retry = bucket_ids(expr_dir, "no_patch") | bucket_ids(
            expr_dir, "raw_patch_but_unparsed"
        )
        missing = sorted(set(missing) | retry)

    for iid in missing:
        print(iid)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
