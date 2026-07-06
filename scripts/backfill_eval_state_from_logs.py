#!/usr/bin/env python3
"""Backfill eval_state.json elapsed_s from pilot_eval.log (one-time / legacy runs)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_LINE = re.compile(
    r"^=== Eval: (?P<id>.+?) @ (?P<ts>\d{4}-\d{2}-\d{2}T[\d:.]+) ===$"
)


def parse_eval_durations(log_path: Path) -> dict[str, float]:
    """Map instance_id -> elapsed_s using gaps between consecutive eval start lines."""
    if not log_path.is_file():
        return {}
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[tuple[str, datetime]] = []
    for line in lines:
        m = EVAL_LINE.match(line.strip())
        if m:
            events.append((m.group("id"), datetime.fromisoformat(m.group("ts"))))

    durations: dict[str, float] = {}
    for i, (iid, start) in enumerate(events):
        if i + 1 < len(events):
            elapsed = (events[i + 1][1] - start).total_seconds()
        else:
            elapsed = 60.0
        durations[iid] = max(1.0, round(elapsed, 1))
    return durations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expr-dir",
        type=Path,
        default=ROOT / "experiment" / "deepseek-lite-pilot",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=ROOT / "pilot_eval.log",
        help="Log containing '=== Eval: instance @ iso ===' lines",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing elapsed_s entries",
    )
    args = parser.parse_args()

    expr_dir = args.expr_dir.resolve()
    state_path = expr_dir / "eval_state.json"
    state: dict = {"instances": {}}
    if state_path.is_file():
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded.get("instances"), dict):
            state = loaded

    durations = parse_eval_durations(args.log_file.resolve())
    if not durations:
        print(f"No eval timing lines in {args.log_file}", file=sys.stderr)
        return 1

    updated = 0
    for iid, elapsed_s in durations.items():
        entry = state["instances"].setdefault(iid, {})
        if entry.get("elapsed_s") and not args.overwrite:
            continue
        entry["elapsed_s"] = elapsed_s
        entry["status"] = entry.get("status") or "done"
        entry["note"] = entry.get("note") or "backfilled from pilot_eval.log"
        updated += 1

    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    print(f"Updated {updated} instance(s) -> {state_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
