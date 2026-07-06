"""
Patch-side pattern linter and DiffRegressionEngine (HD).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app import config
from app.knowledge.contract_features import (
    extract_from_intended_behavior,
    extract_from_source,
)

if TYPE_CHECKING:
    from app.data_structures import BugLocation


@dataclass
class PatchLintFinding:
    rule_id: str
    severity: str
    remediation: str


class DiffRegressionEngine:
    def check(
        self,
        diff_path: str,
        project_path: str,
        artifact: dict | None,
        bug_locs: list[BugLocation],
        prev_diff_path: str | None = None,
    ) -> list[PatchLintFinding]:
        if not config.enable_sympy_pipeline_v2:
            return []

        findings: list[PatchLintFinding] = []
        artifact = artifact or {}
        sibling_scan = artifact.get("sibling_scan", [])

        if not sibling_scan:
            findings.append(
                PatchLintFinding(
                    "PL_ARTIFACT_MISSING",
                    "warn",
                    "no localization_artifact.json sibling_scan — skipping PL_INCOMPLETE_COVERAGE",
                )
            )
        else:
            findings.extend(
                _check_incomplete_coverage(diff_path, project_path, sibling_scan)
            )

        if prev_diff_path:
            findings.extend(
                _check_delegation_regression(diff_path, prev_diff_path, project_path)
            )
        else:
            findings.extend(
                _check_intended_delegation_drift(diff_path, project_path, bug_locs)
            )

        return findings


def _normalize_file(file_path: str) -> str:
    return file_path.replace("\\", "/").removeprefix("a/").removeprefix("b/")


def _check_incomplete_coverage(
    diff_path: str, project_path: str, sibling_scan: list[dict]
) -> list[PatchLintFinding]:
    from app.api.validation import get_changed_methods

    findings: list[PatchLintFinding] = []
    try:
        changed = get_changed_methods(diff_path, project_path)
    except Exception as e:
        return [
            PatchLintFinding(
                "PL_DIFF_APPLY_FAIL",
                "warn",
                f"could not apply diff for coverage check: {e}",
            )
        ]

    for row in sibling_scan:
        if str(row.get("needs_fix", "")).lower() != "yes":
            continue
        cls = row.get("class", "")
        method = row.get("method_or_handler", "")
        file_path = _normalize_file(row.get("file", ""))
        touched = False
        for fpath, methods in changed.items():
            nf = _normalize_file(fpath)
            if file_path and nf != file_path and not nf.endswith(file_path):
                continue
            for mid in methods:
                if mid.method_name == method and (not cls or mid.class_name == cls):
                    touched = True
        if not touched:
            findings.append(
                PatchLintFinding(
                    "PL_INCOMPLETE_COVERAGE",
                    "block",
                    f"diff does not touch needs_fix=yes handler {cls}.{method}",
                )
            )
    return findings


def _diff_feature_counts(diff_path: str, project_path: str) -> tuple[int, int]:
    """Return (self_print_count, inline_literal_count) heuristic from patched files."""
    from app.api.validation import get_changed_methods

    try:
        changed = get_changed_methods(diff_path, project_path)
    except Exception:
        return 0, 0
    self_print = 0
    inline = 0
    content = Path(diff_path).read_text()
    self_print += content.count("self._print(")
    inline += content.count('f"') + content.count("f'")
    return self_print, inline


def _check_delegation_regression(
    diff_path: str, prev_diff_path: str, project_path: str
) -> list[PatchLintFinding]:
    findings: list[PatchLintFinding] = []
    cur_sp, cur_inl = _diff_feature_counts(diff_path, project_path)
    prev_sp, prev_inl = _diff_feature_counts(prev_diff_path, project_path)
    if prev_sp > cur_sp and cur_inl > prev_inl:
        findings.append(
            PatchLintFinding(
                "PL_DELEGATION_REGRESSION",
                "block",
                "self._print usage decreased while inline literals increased vs previous patch",
            )
        )
    if cur_inl - prev_inl > 3 and cur_sp < prev_sp:
        findings.append(
            PatchLintFinding(
                "PL_INLINE_SURGE",
                "block",
                "inline string surge with AST delegation removal",
            )
        )
    return findings


def _check_intended_delegation_drift(
    diff_path: str, project_path: str, bug_locs: list[BugLocation]
) -> list[PatchLintFinding]:
    findings: list[PatchLintFinding] = []
    if not bug_locs:
        return findings

    diff_text = Path(diff_path).read_text()
    for loc in bug_locs:
        ib_fs = extract_from_intended_behavior(loc.intended_behavior)
        neighbor_fs = extract_from_source(loc.code, loc.method_name)
        if ib_fs.has_self_print or (neighbor_fs and neighbor_fs.has_self_print):
            if "self._print(" not in diff_text:
                findings.append(
                    PatchLintFinding(
                        "PL_INTENDED_DELEGATION_DRIFT",
                        "warn",
                        f"IB/neighbor expect delegation but diff lacks self._print for {loc.method_name}",
                    )
                )
    return findings


def lint_patch(
    diff_path: str,
    project_path: str,
    artifact_path: str | None,
    bug_locs: list[BugLocation],
    prev_diff_path: str | None = None,
) -> list[PatchLintFinding]:
    artifact = None
    if artifact_path and Path(artifact_path).is_file():
        artifact = json.loads(Path(artifact_path).read_text())
    engine = DiffRegressionEngine()
    return engine.check(
        diff_path, project_path, artifact, bug_locs, prev_diff_path=prev_diff_path
    )


def has_blocking_patch_findings(findings: list[PatchLintFinding]) -> bool:
    return any(f.severity == "block" for f in findings)
