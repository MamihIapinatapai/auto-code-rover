#!/usr/bin/env python3
"""Split conf/swe_lite_tasks.txt into per-repo lists under conf/lite300_tasks/."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "conf" / "swe_lite_tasks.txt"
OUT_DIR = ROOT / "conf" / "lite300_tasks"

PREFIX_TO_REPO: list[tuple[str, str]] = [
    ("django__", "django"),
    ("sympy__", "sympy"),
    ("matplotlib__", "matplotlib"),
    ("scikit-learn__", "scikit-learn"),
    ("pytest-dev__", "pytest"),
    ("sphinx-doc__", "sphinx"),
    ("astropy__", "astropy"),
    ("psf__", "requests"),
    ("pylint-dev__", "pylint"),
    ("pydata__", "xarray"),
    ("mwaskom__", "seaborn"),
    ("pallets__", "flask"),
]


def repo_for(instance_id: str) -> str:
    for prefix, repo in PREFIX_TO_REPO:
        if instance_id.startswith(prefix):
            return repo
    raise ValueError(f"Unknown instance_id prefix: {instance_id}")


def main() -> None:
    lines = [
        ln.strip()
        for ln in SOURCE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    buckets: dict[str, list[str]] = {repo: [] for _, repo in PREFIX_TO_REPO}
    for iid in lines:
        buckets[repo_for(iid)].append(iid)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    for repo in sorted(buckets):
        tasks = buckets[repo]
        counts[repo] = len(tasks)
        (OUT_DIR / f"{repo}.txt").write_text("\n".join(tasks) + "\n", encoding="utf-8")

    total = sum(counts.values())
    print(f"Wrote {len(counts)} repo files under {OUT_DIR} ({total} tasks)")
    for repo, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {repo}: {n}")


if __name__ == "__main__":
    main()
