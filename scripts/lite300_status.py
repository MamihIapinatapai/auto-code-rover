#!/usr/bin/env python3
"""Lite 300 progress table with per-instance deduplication."""

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

LITE300_REPOS = [
    "django",
    "sympy",
    "matplotlib",
    "scikit-learn",
    "pytest",
    "sphinx",
    "astropy",
    "requests",
    "pylint",
    "xarray",
    "seaborn",
    "flask",
]

# Phase1 run order (ascending task count)
PHASE1_ORDER = [
    "flask",
    "seaborn",
    "xarray",
    "astropy",
    "requests",
    "pylint",
    "sphinx",
    "pytest",
    "matplotlib",
    "scikit-learn",
    "sympy",
    "django",
]

BUCKETS = ("applicable_patch", "no_patch", "raw_patch_but_unparsed")


def load_task_ids(tasks_file: Path) -> list[str]:
    return [
        ln.strip()
        for ln in tasks_file.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def ids_in_bucket(expr_dir: Path, bucket: str) -> set[str]:
    bucket_dir = expr_dir / bucket
    if not bucket_dir.is_dir():
        return set()
    out: set[str] = set()
    for task_dir in bucket_dir.iterdir():
        if task_dir.is_dir():
            out.add(instance_id_from_task_dir(task_dir))
    return out


def pred_ids_from_json(expr_dir: Path) -> set[str]:
    pred_path = expr_dir / "predictions_for_swebench.json"
    if not pred_path.is_file():
        return set()
    data = json.loads(pred_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {str(p["instance_id"]) for p in data}
    return {str(k) for k in data.keys()}


def l3_done(sync_dir: Path, expected: int | None = None) -> bool:
    report = sync_dir / "report" / "report.json"
    if report.is_file():
        return True
    progress = sync_dir / "eval_progress.json"
    if not progress.is_file():
        return False
    try:
        prog = json.loads(progress.read_text(encoding="utf-8"))
        done_list = prog.get("done")
        if isinstance(done_list, list) and expected is not None:
            return len(done_list) >= expected
        total = prog.get("total") or prog.get("expected")
        done = prog.get("completed") or prog.get("done")
        if total and done is not None:
            if isinstance(done, list):
                return len(done) >= int(total)
            return int(done) >= int(total)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return False


def repo_stats(repo: str, base: Path) -> dict:
    tasks_file = base / "conf" / "lite300_tasks" / f"{repo}.txt"
    expr_dir = base / "experiment" / "deepseek-lite-300" / "repos" / repo
    sync_dir = base / "lite300_output" / "repos" / repo

    expected_ids = load_task_ids(tasks_file) if tasks_file.is_file() else []
    exp = len(expected_ids)
    pred = pred_ids_from_json(expr_dir)
    appl = ids_in_bucket(expr_dir, "applicable_patch")
    no = ids_in_bucket(expr_dir, "no_patch")
    unpar = ids_in_bucket(expr_dir, "raw_patch_but_unparsed")

    missing = set(expected_ids) - pred if expected_ids else set()

    return {
        "repo": repo,
        "exp": exp,
        "pred": len(pred),
        "appl": len(appl),
        "no": len(no),
        "unpar": len(unpar),
        "missing_n": len(missing),
        "l3": "Y" if l3_done(sync_dir, exp) else "-",
        "verify_hint": "ok" if exp and len(pred) == exp and not no and not missing else "gap",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lite 300 deduplicated progress table.")
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT,
        help="Repository root (default: auto-code-rover root)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Show only one repo",
    )
    args = parser.parse_args()

    repos = [args.repo] if args.repo else PHASE1_ORDER
    rows = [repo_stats(r, args.base) for r in repos]

    header = f"{'REPO':<14} {'EXP':>4} {'PRED':>5} {'APPL':>5} {'NO':>4} {'UNPAR':>5} {'MISS':>5} {'L3':>3} {'STATUS':>6}"
    print(header)
    print("-" * len(header))

    tot = {k: 0 for k in ("exp", "pred", "appl", "no", "unpar", "missing_n")}
    for row in rows:
        print(
            f"{row['repo']:<14} {row['exp']:>4} {row['pred']:>5} {row['appl']:>5} "
            f"{row['no']:>4} {row['unpar']:>5} {row['missing_n']:>5} {row['l3']:>3} {row['verify_hint']:>6}"
        )
        for k in tot:
            tot[k] += row[k]

    print("-" * len(header))
    print(
        f"{'TOTAL':<14} {tot['exp']:>4} {tot['pred']:>5} {tot['appl']:>5} "
        f"{tot['no']:>4} {tot['unpar']:>5} {tot['missing_n']:>5}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
