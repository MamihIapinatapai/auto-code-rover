#!/usr/bin/env python3
"""One-shot DeepSWE baseline runner (Phase 1: patch generation only)."""

from __future__ import annotations

import configparser
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from os.path import join as pjoin
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve_project_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def limit_task_list(task_list_path: Path, max_tasks: int | None) -> Path:
    if not max_tasks or max_tasks <= 0:
        return task_list_path
    lines = [
        ln.strip()
        for ln in task_list_path.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    limited = lines[:max_tasks]
    tmp = ROOT / "outputs" / ".deepswe_task_list_limit.txt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("\n".join(limited) + "\n", encoding="utf-8")
    print(f"Limiting to first {len(limited)} task(s): {limited}")
    return tmp


def load_dotenv() -> None:
    env_path = ROOT / "conf" / ".env"
    if not env_path.is_file():
        print(f"WARNING: {env_path} not found", file=sys.stderr)
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_conf(conf_file: Path) -> configparser.SectionProxy:
    config = configparser.ConfigParser()
    with conf_file.open(encoding="utf-8") as f:
        config.read_string("[DEFAULT]\n" + f.read())
    return config["DEFAULT"]


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run DeepSWE patch generation")
    parser.add_argument(
        "--conf-file",
        default=str(ROOT / "conf/deepseek-deepswe.conf"),
        help="Path to DeepSWE experiment config",
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=int(os.environ.get("DEEPSWE_MAX_TASKS", "0") or "0"),
        help="Run only the first N tasks from the list (0 = all).",
    )
    args = parser.parse_args()

    conf_path = Path(args.conf_file).resolve()
    if not conf_path.is_file():
        print(f"Config not found: {conf_path}", file=sys.stderr)
        return 1

    load_dotenv()
    cfg = read_conf(conf_path)

    expr_id = cfg["id"]
    experiment_root = resolve_project_path(cfg["experiment_dir"])
    tasks_dir = resolve_project_path(cfg["deepswe_tasks_dir"])
    repos_dir = resolve_project_path(cfg["deepswe_repos_dir"])
    patches_dir = resolve_project_path(
        cfg.get("patches_dir", "outputs/deepswe_patches")
    )

    selected_tasks = cfg["selected_tasks_file"]
    task_list_path = resolve_project_path(selected_tasks)
    task_list_path = limit_task_list(task_list_path, args.max_tasks or None)

    if not tasks_dir.is_dir():
        print(
            f"DeepSWE tasks dir missing: {tasks_dir}\n"
            f"Run: bash scripts/setup_deepswe.sh",
            file=sys.stderr,
        )
        return 1

    expr_dir = experiment_root / expr_id
    expr_dir.mkdir(parents=True, exist_ok=True)
    repos_dir.mkdir(parents=True, exist_ok=True)
    patches_dir.mkdir(parents=True, exist_ok=True)

    model = cfg["model"].split()
    temperature = cfg.get("temperature", "0.2")
    conv_round_limit = cfg.get("conv_round_limit", "15")
    num_processes = cfg.get("num_processes", "1")
    print_flag = cfg.get("print", "false").lower() in ("1", "true", "yes")

    cmd = [
        sys.executable,
        str(ROOT / "app/main.py"),
        "deepswe",
        "--deepswe-tasks-dir",
        str(tasks_dir),
        "--deepswe-repos-dir",
        str(repos_dir),
        "--deepswe-patches-dir",
        str(patches_dir),
        "--output-dir",
        str(expr_dir),
        "--task-list-file",
        str(task_list_path),
        "--model",
        *model,
        "--model-temperature",
        str(temperature),
        "--conv-round-limit",
        str(conv_round_limit),
        "--num-processes",
        str(num_processes),
    ]
    if not print_flag:
        cmd.append("--no-print")

    if cfg.get("enable_semantic_injection_ver1", "false").lower() in ("1", "true", "yes"):
        cmd.append("--enable-semantic-injection-ver1")
    if cfg.get("enable_spec_parser", "false").lower() in ("1", "true", "yes"):
        cmd.append("--enable-spec-parser")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)

    start = time.time()
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ROOT, env=env)
    elapsed = time.time() - start

    from app.runner.run_deepswe import collect_patches_from_run

    model_name = model[0] if model else "unknown"
    patch_stats = collect_patches_from_run(str(expr_dir), str(patches_dir), model_name=model_name)

    stats = {
        "expr_id": expr_id,
        "experiment_dir": str(expr_dir),
        "patches_dir": str(patches_dir),
        "elapsed_s": round(elapsed, 1),
        "exit_code": result.returncode,
        "patch_stats": patch_stats,
        "finished_at": datetime.now().isoformat(),
    }
    stats_path = expr_dir / "stats.json"
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"Wrote stats to {stats_path}")
    print(
        f"Patches: {patch_stats.get('with_patch', 0)} with patch, "
        f"{patch_stats.get('no_patch', 0)} empty"
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
