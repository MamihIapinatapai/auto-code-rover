#!/usr/bin/env python3
"""Validate DeepSWE tasks directory and generate task list files."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <tasks_dir> <conf_dir>", file=sys.stderr)
        return 1

    tasks_dir = Path(sys.argv[1]).resolve()
    conf_dir = Path(sys.argv[2]).resolve()
    manifest_path = tasks_dir / "manifest.json"

    if not manifest_path.is_file():
        print(f"ERROR: missing {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks", [])
    task_count = manifest.get("task_count", len(tasks))

    missing: list[str] = []
    for entry in tasks:
        task_id = entry["task_id"]
        task_path = tasks_dir / task_id
        if not (task_path / "task.toml").is_file():
            missing.append(f"{task_id}: missing task.toml")
        if not (task_path / "instruction.md").is_file():
            missing.append(f"{task_id}: missing instruction.md")

    if missing:
        print("ERROR: incomplete task directories:", file=sys.stderr)
        for line in missing[:20]:
            print(f"  {line}", file=sys.stderr)
        return 1

    all_ids = sorted(entry["task_id"] for entry in tasks)
    python_ids = sorted(
        entry["task_id"] for entry in tasks if entry.get("language") == "python"
    )

    conf_dir.mkdir(parents=True, exist_ok=True)
    all_file = conf_dir / "deepswe_all_tasks.txt"
    python_file = conf_dir / "deepswe_python_tasks.txt"
    all_file.write_text("\n".join(all_ids) + "\n", encoding="utf-8")
    python_file.write_text("\n".join(python_ids) + "\n", encoding="utf-8")

    print(f"DeepSWE manifest task_count={task_count}, entries={len(tasks)}")
    print(f"Validated {len(all_ids)} task directories under {tasks_dir}")
    print(f"Python tasks: {len(python_ids)}")
    print(f"Wrote {all_file}")
    print(f"Wrote {python_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
