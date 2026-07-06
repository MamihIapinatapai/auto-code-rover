#!/usr/bin/env python3
"""Pre-flight checks for AutoCodeRover replication (see SERVER_REPLICATION_GUIDE §3.2)."""

from __future__ import annotations

import ast
import os
import subprocess
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


def main() -> int:
    all_ok = True

    # agent_search: analyze-and-select phase (third LLM step per round)
    src = (ROOT / "app/agents/agent_search.py").read_text()
    all_ok &= check(
        "agent_search.py third yield",
        "Model response (analyze and select)" in src
        and src.count("yield res_text, msg_thread") >= 2,
    )

    cfg = (ROOT / "app/config.py").read_text()
    all_ok &= check(
        "backup_model uses DeepSeek",
        "litellm-generic-deepseek/deepseek-chat" in cfg,
    )
    all_ok &= check("enable_text_only_search in config", "enable_text_only_search" in cfg)

    common = (ROOT / "app/model/common.py").read_text()
    all_ok &= check(
        "max_tokens int cast",
        "max_tokens=int(os.getenv" in common,
    )

    all_ok &= check("conf/deepseek-lite.conf", (ROOT / "conf/deepseek-lite.conf").is_file())
    all_ok &= check("conf/pilot_tasks.txt", (ROOT / "conf/pilot_tasks.txt").is_file())
    all_ok &= check("demo_pilot sample", (ROOT / "demo_pilot/sample_project/calculator.py").is_file())

    if os.getenv("DEEPSEEK_API_KEY"):
        all_ok &= check("DEEPSEEK_API_KEY", True)
    else:
        all_ok &= check("DEEPSEEK_API_KEY", False, "not set in environment")

    token_limit = os.getenv("ACR_TOKEN_LIMIT", "1024")
    all_ok &= check("ACR_TOKEN_LIMIT", int(token_limit) >= 4096, f"value={token_limit}")

    in_experiment_image = Path("/opt/SWE-bench/setup_result/setup_map.json").exists()
    if in_experiment_image:
        all_ok &= check("SWE-bench setup_map.json", True)
        all_ok &= check("SWE-bench tasks_map.json", Path("/opt/SWE-bench/setup_result/tasks_map.json").exists())
    else:
        check("SWE-bench setup (host)", False, "skipped — not in experiment container")

    # docker daemon: skip inside experiment container (no docker CLI)
    if Path("/.dockerenv").exists() or os.getenv("ACR_SKIP_DOCKER_CHECK") == "1":
        check("docker daemon", True, "skipped inside container")
    else:
        try:
            cp = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            all_ok &= check("docker daemon", cp.returncode == 0)
        except FileNotFoundError:
            all_ok &= check("docker daemon", False, "docker CLI not found")

    print("---")
    if all_ok:
        print("All prerequisite checks PASSED.")
        return 0
    print("Some checks FAILED.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
