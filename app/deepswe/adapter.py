"""Parse DeepSWE Harbor-format task directories."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from app.deepswe.types import DeepSweTaskRecord

_GITHUB_REPO_RE = re.compile(r"github\.com[/:]([^/]+)/([^/.]+)")


def parse_repo_name(repository_url: str) -> str:
    match = _GITHUB_REPO_RE.search(repository_url.rstrip("/"))
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    parsed = urlparse(repository_url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    raise ValueError(f"Cannot parse repo name from URL: {repository_url}")


def _read_task_toml(task_dir: Path) -> dict:
    data = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    metadata = data.get("metadata") or {}
    return metadata


def load_task(task_dir: str | Path) -> DeepSweTaskRecord:
    task_path = Path(task_dir).resolve()
    task_id = task_path.name
    metadata = _read_task_toml(task_path)

    instance_id = metadata.get("task_id") or task_id
    repo_url = metadata.get("repository_url", "")
    if not repo_url:
        raise ValueError(f"{task_path}: missing metadata.repository_url")

    base_commit = metadata.get("base_commit_hash", "")
    if not base_commit:
        raise ValueError(f"{task_path}: missing metadata.base_commit_hash")

    instruction_path = task_path / "instruction.md"
    if not instruction_path.is_file():
        raise ValueError(f"{task_path}: missing instruction.md")

    repo_name = metadata.get("repo") or parse_repo_name(repo_url)
    language = (metadata.get("language") or "unknown").lower()

    return DeepSweTaskRecord(
        instance_id=instance_id,
        problem_statement=instruction_path.read_text(encoding="utf-8"),
        repo_url=repo_url.rstrip("/"),
        repo_name=repo_name,
        base_commit=base_commit,
        language=language,
        task_dir=task_path,
    )


def load_manifest(manifest_path: str | Path) -> list[DeepSweTaskRecord]:
    manifest_file = Path(manifest_path).resolve()
    tasks_root = manifest_file.parent
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    records: list[DeepSweTaskRecord] = []
    for entry in manifest.get("tasks", []):
        task_id = entry["task_id"]
        records.append(load_task(tasks_root / task_id))
    return records


def filter_by_language(
    tasks: list[DeepSweTaskRecord], language: str
) -> list[DeepSweTaskRecord]:
    lang = language.lower()
    return [t for t in tasks if t.language == lang]
