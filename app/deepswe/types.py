"""Data types for DeepSWE Harbor tasks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeepSweTaskRecord:
    instance_id: str
    problem_statement: str
    repo_url: str
    repo_name: str
    base_commit: str
    language: str
    task_dir: Path
