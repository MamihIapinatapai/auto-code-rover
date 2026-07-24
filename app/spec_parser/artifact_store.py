"""Artifact persistence helpers for Spec Parser v3.4 (WP-ART)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from loguru import logger

from app import config

_SCRIPT_NAMES = ("test_feature.py", "reproduce_issue.py")


def script_paths(output_dir: Path) -> list[Path]:
    return [output_dir / name for name in _SCRIPT_NAMES if (output_dir / name).exists()]


def disk_script_present(output_dir: Path) -> bool:
    return bool(script_paths(output_dir))


def quarantine_or_delete_scripts(output_dir: Path, *, reason: str = "no_script") -> list[str]:
    """Remove or isolate unselected scripts when final_action=no_script (ART-M1)."""
    if not getattr(config, "spec_parser_delete_script_on_no_script", True):
        return []
    if not getattr(config, "spec_parser_enable_artifact_store", True):
        return []
    touched: list[str] = []
    quarantine = output_dir / "_quarantine_rejected_scripts"
    for path in script_paths(output_dir):
        try:
            quarantine.mkdir(parents=True, exist_ok=True)
            dest = quarantine / f"{reason}__{path.name}"
            if dest.exists():
                dest.unlink()
            shutil.move(str(path), str(dest))
            touched.append(str(dest.relative_to(output_dir)))
            logger.info("ART: quarantined {} -> {}", path.name, dest)
        except OSError as exc:
            logger.warning("ART: failed to quarantine {}: {}", path, exc)
            try:
                path.unlink()
                touched.append(f"deleted:{path.name}")
            except OSError:
                pass
    return touched


def write_artifact_consistency_report(
    output_dir: Path,
    *,
    final_action: str,
    selected_draft_id: str = "",
    accepted_script_present: bool | None = None,
) -> dict:
    disk = disk_script_present(output_dir)
    if accepted_script_present is None:
        accepted_script_present = disk and final_action in (
            "calib_pass",
            "persist",
            "s1_accept",
        )
    if final_action == "no_script" and disk:
        quarantine_or_delete_scripts(output_dir, reason="no_script")
        disk = disk_script_present(output_dir)
        accepted_script_present = False
    report = {
        "final_action": final_action,
        "selected_draft_id": selected_draft_id,
        "disk_script_present": disk,
        "accepted_script_present": bool(accepted_script_present),
        "artifact_consistent": (
            (final_action == "no_script" and not disk)
            or (final_action != "no_script" and disk == bool(accepted_script_present))
        ),
    }
    (output_dir / "artifact_consistency.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report
