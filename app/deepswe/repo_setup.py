"""Git cache and per-task work copies for DeepSWE."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from app.deepswe.adapter import parse_repo_name
from app.deepswe.types import DeepSweTaskRecord
from app.log import log_and_print


def cache_key_for(record: DeepSweTaskRecord) -> str:
    owner, repo = parse_repo_name(record.repo_url).split("/", 1)
    commit_short = record.base_commit[:12]
    return f"{owner}__{repo}@{commit_short}"


def _clone_url(record: DeepSweTaskRecord) -> str:
    clone_url = record.repo_url.rstrip("/")
    if not clone_url.endswith(".git"):
        clone_url = f"{clone_url}.git"
    return clone_url


def _shallow_clone_at_commit(clone_url: str, commit: str, dest: Path) -> None:
    """Fetch a single revision (faster and more reliable than full clone)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)

    # Network hangs without a timeout (e.g. Textualize/textual); fail fast for retries.
    fetch_timeout_sec = int(os.environ.get("DEEPSWE_GIT_FETCH_TIMEOUT_SEC", "180"))

    subprocess.run(["git", "init", str(dest)], check=True, capture_output=True)
    subprocess.run(
        ["git", "remote", "add", "origin", clone_url],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    try:
        fetch = subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", commit],
            cwd=dest,
            capture_output=True,
            text=True,
            timeout=fetch_timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"git fetch --depth 1 timed out after {fetch_timeout_sec}s for {clone_url}@{commit}"
        ) from exc
    if fetch.returncode != 0:
        # Fallback: unshallow fetch then checkout
        try:
            subprocess.run(
                ["git", "fetch", "origin", commit],
                cwd=dest,
                check=True,
                capture_output=True,
                text=True,
                timeout=fetch_timeout_sec,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"git fetch timed out after {fetch_timeout_sec}s for {clone_url}@{commit}"
            ) from exc
    subprocess.run(["git", "checkout", "FETCH_HEAD"], cwd=dest, check=True, capture_output=True)
    subprocess.run(["git", "reset", "--hard", commit], cwd=dest, check=True, capture_output=True)


def _ensure_cache(record: DeepSweTaskRecord, repos_root: Path) -> Path:
    cache_dir = repos_root / "cache" / cache_key_for(record)
    if cache_dir.is_dir() and (cache_dir / ".git").is_dir():
        return cache_dir

    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    clone_url = _clone_url(record)
    log_and_print(
        f"[DeepSWE] Cloning cache {record.repo_name}@{record.base_commit[:12]} ..."
    )

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            _shallow_clone_at_commit(clone_url, record.base_commit, cache_dir)
            return cache_dir
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            log_and_print(
                f"[DeepSWE] Clone attempt {attempt}/3 failed for {record.repo_name}: {exc}"
            )
            time.sleep(5 * attempt)

    raise RuntimeError(
        f"Failed to clone {record.repo_name}@{record.base_commit}"
    ) from last_error


def ensure_work_copy(record: DeepSweTaskRecord, repos_root: str | Path) -> Path:
    """Return isolated writable repo path for one DeepSWE instance."""
    root = Path(repos_root).resolve()
    cache_dir = _ensure_cache(record, root)
    work_dir = root / "work" / record.instance_id

    if not work_dir.is_dir():
        log_and_print(f"[DeepSWE] Creating work copy for {record.instance_id}")
        if work_dir.exists():
            shutil.rmtree(work_dir)
        shutil.copytree(cache_dir, work_dir, symlinks=True)
    else:
        from app import utils as app_utils

        with app_utils.cd(work_dir):
            app_utils.repo_reset_and_clean_checkout(record.base_commit)

    return work_dir

