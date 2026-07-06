#!/usr/bin/env python3
"""Shared Lite 300 per-instance helpers and pipeline profile resolution."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INSTANCE_REPO_MAP: dict[str, str] = {
    "scikit-learn": "scikit-learn",
    "pytest-dev": "pytest",
    "sphinx-doc": "sphinx",
    "pylint-dev": "pylint",
    "django": "django",
    "matplotlib": "matplotlib",
    "astropy": "astropy",
    "sympy": "sympy",
    "mwaskom": "seaborn",
    "pallets": "flask",
    "psf": "requests",
    "pydata": "xarray",
}


@dataclass(frozen=True)
class PipelineProfile:
    """Experiment/sync directory layout for per-instance L2→L3→Feishu pipeline."""

    name: str
    experiment_prefix: str  # e.g. experiment/deepseek-lite-300/repos
    sync_prefix: str  # e.g. lite300_output/repos


PIPELINE_PROFILES: dict[str, PipelineProfile] = {
    "baseline": PipelineProfile(
        name="baseline",
        experiment_prefix="experiment/deepseek-lite-300/repos",
        sync_prefix="lite300_output/repos",
    ),
    "ver1": PipelineProfile(
        name="ver1",
        experiment_prefix="experiment/deepseek-lite-300-ver1/repos",
        sync_prefix="lite300_output_ver1/repos",
    ),
    "ver1.1": PipelineProfile(
        name="ver1.1",
        experiment_prefix="experiment/deepseek-lite-300-ver1.1/repos",
        sync_prefix="lite300_output_ver1.1/repos",
    ),
    "spec_parser_ver1": PipelineProfile(
        name="spec_parser_ver1",
        experiment_prefix="experiment/deepseek-lite-300-spec-parser-ver1/repos",
        sync_prefix="lite300_output_spec_parser_ver1/repos",
    ),
}


def resolve_pipeline_profile(name: str | None = None) -> PipelineProfile:
    """
    Resolve pipeline profile for path and state file layout.

    Priority: explicit name > PIPELINE_PROFILE env > SYSTEM_VERSION heuristic
    > baseline. Optional PIPELINE_EXPERIMENT_PREFIX / PIPELINE_SYNC_PREFIX override
    paths for custom experiments.
    """
    if name is None:
        name = os.environ.get("PIPELINE_PROFILE", "").strip()
    if not name:
        sv = os.environ.get("SYSTEM_VERSION", "").strip().lower()
        if sv == "ver1.1":
            name = "ver1.1"
        elif sv == "ver1":
            name = "ver1"
        else:
            name = "baseline"

    base = PIPELINE_PROFILES.get(name)
    if base is None:
        exp = os.environ.get("PIPELINE_EXPERIMENT_PREFIX", "").strip()
        sync = os.environ.get("PIPELINE_SYNC_PREFIX", "").strip()
        if not exp or not sync:
            known = ", ".join(sorted(PIPELINE_PROFILES))
            raise ValueError(
                f"Unknown PIPELINE_PROFILE={name!r}. Known: {known}. "
                "For custom profiles set PIPELINE_EXPERIMENT_PREFIX and PIPELINE_SYNC_PREFIX."
            )
        base = PipelineProfile(name=name, experiment_prefix=exp.rstrip("/"), sync_prefix=sync.rstrip("/"))
    else:
        exp_override = os.environ.get("PIPELINE_EXPERIMENT_PREFIX", "").strip()
        sync_override = os.environ.get("PIPELINE_SYNC_PREFIX", "").strip()
        if exp_override or sync_override:
            base = PipelineProfile(
                name=base.name,
                experiment_prefix=exp_override.rstrip("/") if exp_override else base.experiment_prefix,
                sync_prefix=sync_override.rstrip("/") if sync_override else base.sync_prefix,
            )
    return base


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


def repo_from_instance_id(instance_id: str) -> str | None:
    for prefix, repo in INSTANCE_REPO_MAP.items():
        if instance_id.startswith(prefix + "__"):
            return repo
    return None


def _profile_or_default(profile: PipelineProfile | None) -> PipelineProfile:
    return profile if profile is not None else resolve_pipeline_profile()


def expr_dir_for_repo(
    base: Path,
    repo: str,
    profile: PipelineProfile | None = None,
) -> Path:
    prof = _profile_or_default(profile)
    return base / prof.experiment_prefix / repo


def sync_dir_for_repo(
    base: Path,
    repo: str,
    profile: PipelineProfile | None = None,
) -> Path:
    prof = _profile_or_default(profile)
    return base / prof.sync_prefix / repo


def relative_expr_dir(repo: str, profile: PipelineProfile | None = None) -> str:
    prof = _profile_or_default(profile)
    return f"{prof.experiment_prefix}/{repo}"


def relative_sync_dir(repo: str, profile: PipelineProfile | None = None) -> str:
    prof = _profile_or_default(profile)
    return f"{prof.sync_prefix}/{repo}"


def expr_dir_for_instance(
    base: Path,
    instance_id: str,
    profile: PipelineProfile | None = None,
) -> Path | None:
    repo = repo_from_instance_id(instance_id)
    if repo is None:
        return None
    return expr_dir_for_repo(base, repo, profile)


def sync_dir_for_instance(
    base: Path,
    instance_id: str,
    profile: PipelineProfile | None = None,
) -> Path | None:
    repo = repo_from_instance_id(instance_id)
    if repo is None:
        return None
    return sync_dir_for_repo(base, repo, profile)


def pipeline_logs_dir(base: Path, profile: PipelineProfile | None = None) -> Path:
    prof = _profile_or_default(profile)
    return base / "lite300_logs" / "profiles" / prof.name


def retry_state_file(base: Path, profile: PipelineProfile | None = None) -> Path:
    return pipeline_logs_dir(base, profile) / "l2_retry_state.json"


def terminal_state_file(base: Path, profile: PipelineProfile | None = None) -> Path:
    return pipeline_logs_dir(base, profile) / "instance_pipeline_terminal.json"


def instance_pipeline_log_file(base: Path, profile: PipelineProfile | None = None) -> Path:
    return pipeline_logs_dir(base, profile) / "instance_pipeline.log"


def load_task_ids(tasks_file: Path | str) -> list[str]:
    path = Path(tasks_file)
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def load_master_task_ids(base: Path | None = None) -> list[str]:
    base = base or ROOT
    return load_task_ids(base / "conf" / "swe_lite_tasks.txt")


def find_task_dir(expr_dir: Path, instance_id: str, bucket: str) -> Path | None:
    bucket_dir = expr_dir / bucket
    if not bucket_dir.is_dir():
        return None
    for task_dir in bucket_dir.iterdir():
        if task_dir.is_dir() and instance_id_from_task_dir(task_dir) == instance_id:
            return task_dir
    return None


def conf_file_for_repo(repo: str, profile: PipelineProfile | None = None) -> Path:
    """Return host-relative conf path for L2 rerun (profile-aware)."""
    prof = _profile_or_default(profile)
    if prof.name in ("ver1", "ver1.1", "spec_parser_ver1"):
        versioned_conf = ROOT / "conf" / f"deepseek-lite-300-{prof.name}.{repo}.conf"
        if versioned_conf.is_file():
            return versioned_conf
    return ROOT / "conf" / "generated" / f"deepseek-lite-300-{repo}.conf"
