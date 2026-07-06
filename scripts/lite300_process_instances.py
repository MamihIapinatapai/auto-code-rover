#!/usr/bin/env python3
"""Per-instance Lite 300 pipeline: L2 verify → L3 → Feishu (with L2 retries)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lite300_instance_utils import (  # noqa: E402
    PipelineProfile,
    expr_dir_for_instance,
    expr_dir_for_repo,
    instance_pipeline_log_file,
    load_master_task_ids,
    load_task_ids,
    relative_expr_dir,
    relative_sync_dir,
    resolve_pipeline_profile,
    retry_state_file,
    sync_dir_for_instance,
    sync_dir_for_repo,
    terminal_state_file,
)
from verify_l2_instance import verify_l2_instance  # noqa: E402

LOGS_DIR = ROOT / "lite300_logs"
DEFAULT_SKIP_FILE = LOGS_DIR / "feishu_skip_instances.txt"
MAX_L2_RETRIES = 3


def python_exe() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.is_file():
        return str(venv)
    return sys.executable


def load_env_file() -> None:
    env_path = ROOT / "conf" / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path)
        return
    except ImportError:
        pass
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_json_set(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return set(str(x) for x in data)
    if isinstance(data, dict):
        return set(str(k) for k in data.keys())
    return set()


def load_retry_state(profile: PipelineProfile) -> dict[str, int]:
    path = retry_state_file(ROOT, profile)
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.items()}


def save_retry_state(state: dict[str, int], profile: PipelineProfile) -> None:
    path = retry_state_file(ROOT, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def reset_retry_state(instance_ids: list[str], profile: PipelineProfile) -> None:
    state = load_retry_state(profile)
    for iid in instance_ids:
        state.pop(iid, None)
    save_retry_state(state, profile)


def load_terminal(profile: PipelineProfile) -> set[str]:
    return load_json_set(terminal_state_file(ROOT, profile))


def mark_terminal(instance_id: str, terminal: set[str], profile: PipelineProfile) -> None:
    terminal.add(instance_id)
    path = terminal_state_file(ROOT, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(terminal), indent=2), encoding="utf-8")


def log(msg: str, profile: PipelineProfile) -> None:
    line = f"[{datetime.now().isoformat()}] {msg}"
    print(line, flush=True)
    log_path = instance_pipeline_log_file(ROOT, profile)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    legacy = LOGS_DIR / "instance_pipeline.log"
    if log_path != legacy:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        with legacy.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    if cmd and cmd[0].endswith(".py"):
        cmd = [python_exe(), *cmd]
    return subprocess.run(cmd, cwd=ROOT, check=check, text=True, env=os.environ)


def build_skip_set(skip_file: Path | None, profile: PipelineProfile) -> set[str]:
    skip: set[str] = set()
    if skip_file and skip_file.is_file():
        skip |= {
            ln.strip()
            for ln in skip_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        }
    if profile.name == "baseline":
        for repo in ("flask", "seaborn", "astropy", "requests", "pylint"):
            progress = sync_dir_for_repo(ROOT, repo, profile) / "eval_progress.json"
            if progress.is_file():
                skip |= set(json.loads(progress.read_text(encoding="utf-8")).get("done", []))
    return skip


def upsert_l3(
    instance_id: str,
    system_version: str,
    profile: PipelineProfile,
    *,
    dry_run: bool,
    log_fn,
) -> None:
    sync_dir = sync_dir_for_instance(ROOT, instance_id, profile)
    if sync_dir is None:
        raise RuntimeError(f"No sync dir for {instance_id}")
    cmd = [
        python_exe(),
        str(ROOT / "scripts" / "upload_results.py"),
        "--system_version",
        system_version,
        "--log_path",
        str(sync_dir),
        "--instance-id",
        instance_id,
    ]
    if dry_run:
        cmd.append("--dry-run")
    log_fn(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True, text=True, env=os.environ)


def upsert_l2_failure(
    instance_id: str,
    category: str,
    system_version: str,
    profile: PipelineProfile,
    *,
    dry_run: bool,
    error_log: str = "",
    log_fn,
) -> None:
    expr_dir = expr_dir_for_instance(ROOT, instance_id, profile)
    cmd = [
        python_exe(),
        str(ROOT / "scripts" / "upload_results.py"),
        "--system_version",
        system_version,
        "--l2-failure",
        f"{instance_id}:{category}",
    ]
    if error_log:
        cmd.extend(["--l2-error-log", error_log])
    if expr_dir is not None:
        cmd.extend(["--expr-root", str(expr_dir)])
    if dry_run:
        cmd.append("--dry-run")
    log_fn(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True, text=True, env=os.environ)


def run_l3(instance_id: str, profile: PipelineProfile, log_fn) -> None:
    from lite300_instance_utils import repo_from_instance_id

    repo = repo_from_instance_id(instance_id)
    if repo is None:
        raise RuntimeError(f"Unknown repo for {instance_id}")
    env = os.environ.copy()
    env["PIPELINE_PROFILE"] = profile.name
    env["EXPR_DIR"] = relative_expr_dir(repo, profile)
    env["SYNC_DIR"] = relative_sync_dir(repo, profile)
    log_fn(f"L3 eval {instance_id} repo={repo} EXPR_DIR={env['EXPR_DIR']}")
    proc = subprocess.run(
        ["bash", "scripts/run_pilot_eval_incremental.sh", "--resume", "--instance-id", instance_id],
        cwd=ROOT,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"L3 eval failed for {instance_id} (exit {proc.returncode})")


def rerun_l2(instance_id: str, profile: PipelineProfile, log_fn) -> bool:
    env = os.environ.copy()
    env["PIPELINE_PROFILE"] = profile.name
    cmd = ["bash", "scripts/rerun_lite300_one.sh", "--for-pipeline", instance_id]
    log_fn(f"$ PIPELINE_PROFILE={profile.name} {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    if proc.returncode != 0:
        log_fn(f"L2 rerun exit {proc.returncode} for {instance_id}")
        return False
    return True


def process_instance(
    instance_id: str,
    *,
    profile: PipelineProfile,
    system_version: str,
    retry_state: dict[str, int],
    terminal: set[str],
    dry_run: bool,
    log_fn,
) -> None:
    expr_dir = expr_dir_for_instance(ROOT, instance_id, profile)
    if expr_dir is None or not expr_dir.is_dir():
        log_fn(f"SKIP {instance_id}: missing expr dir {expr_dir}")
        return

    while True:
        result = verify_l2_instance(instance_id, expr_dir)
        if result.passed:
            log_fn(f"L2 PASS {instance_id} → L3")
            if not dry_run:
                run_l3(instance_id, profile, log_fn)
                upsert_l3(instance_id, system_version, profile, dry_run=False, log_fn=log_fn)
            else:
                log_fn(f"[dry-run] would L3 + Feishu upsert {instance_id}")
            mark_terminal(instance_id, terminal, profile)
            retry_state.pop(instance_id, None)
            save_retry_state(retry_state, profile)
            return

        retries = retry_state.get(instance_id, 0)
        log_fn(
            f"L2 FAIL {instance_id} category={result.category} "
            f"retries={retries}/{MAX_L2_RETRIES}"
        )

        if retries >= MAX_L2_RETRIES:
            log_fn(f"L2 terminal fail {instance_id} → Feishu {result.category}")
            if not dry_run:
                upsert_l2_failure(
                    instance_id,
                    result.category,
                    system_version,
                    profile,
                    dry_run=False,
                    error_log=result.message,
                    log_fn=log_fn,
                )
            mark_terminal(instance_id, terminal, profile)
            retry_state.pop(instance_id, None)
            save_retry_state(retry_state, profile)
            return

        retry_state[instance_id] = retries + 1
        save_retry_state(retry_state, profile)
        if dry_run:
            log_fn(f"[dry-run] would rerun L2 for {instance_id}")
            return
        if not rerun_l2(instance_id, profile, log_fn):
            log_fn(f"L2 rerun failed {instance_id}; will re-verify and retry")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lite 300 per-instance L2→L3→Feishu pipeline.")
    parser.add_argument(
        "--system-version",
        default=os.environ.get("SYSTEM_VERSION", "Baseline"),
    )
    parser.add_argument(
        "--pipeline-profile",
        default=None,
        help="Pipeline profile name (baseline, ver1, ver1.1). Default: PIPELINE_PROFILE env or baseline",
    )
    parser.add_argument(
        "--skip-file",
        type=Path,
        default=DEFAULT_SKIP_FILE,
        help="Instances to skip (already in Feishu/L3)",
    )
    parser.add_argument(
        "--instances-file",
        type=Path,
        default=None,
        help="Process only these instance ids (default: all 300 minus skip/terminal)",
    )
    parser.add_argument(
        "--reset-retry",
        action="store_true",
        help="Clear l2_retry_state for instances in --instances-file before run",
    )
    parser.add_argument(
        "--ignore-skip",
        action="store_true",
        help="Do not apply feishu_skip_instances / early-repo skip set",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N instances")
    args = parser.parse_args()

    if not (ROOT / "conf" / ".env").is_file():
        print("Missing conf/.env", file=sys.stderr)
        return 1

    load_env_file()
    profile = resolve_pipeline_profile(args.pipeline_profile)

    def log_fn(msg: str) -> None:
        log(msg, profile)

    if args.instances_file:
        todo_all = load_task_ids(args.instances_file)
        if args.reset_retry:
            reset_retry_state(todo_all, profile)
            log_fn(f"Reset retry state for {len(todo_all)} instance(s)")
    else:
        todo_all = load_master_task_ids(ROOT)

    skip: set[str] = set()
    if not args.ignore_skip and not args.instances_file:
        skip = build_skip_set(args.skip_file, profile)

    terminal = load_terminal(profile)
    retry_state = load_retry_state(profile)

    log_fn(
        f"Pipeline start profile={profile.name} system_version={args.system_version} "
        f"experiment_prefix={profile.experiment_prefix} sync_prefix={profile.sync_prefix} "
        f"todo={len(todo_all)} skip={len(skip)} terminal={len(terminal)}"
    )

    todo = [iid for iid in todo_all if iid not in skip and iid not in terminal]

    processed = 0
    for instance_id in todo:
        try:
            process_instance(
                instance_id,
                profile=profile,
                system_version=args.system_version,
                retry_state=retry_state,
                terminal=terminal,
                dry_run=args.dry_run,
                log_fn=log_fn,
            )
        except Exception as exc:
            log_fn(f"ERROR {instance_id}: {exc}")
            time.sleep(5)
            continue

        processed += 1
        if args.limit and processed >= args.limit:
            log_fn(f"Reached --limit {args.limit}")
            break

    log_fn(f"Pipeline pass done processed={processed} terminal={len(load_terminal(profile))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
