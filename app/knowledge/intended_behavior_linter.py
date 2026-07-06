"""
Intended behavior mechanical linter — L1 structural + L2 evidence triangulation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app import config
from app.knowledge.contract_features import (
    FEATURE_COVERAGE_MIN,
    contracts_conflict,
    extract_from_intended_behavior,
    extract_from_issue,
    extract_from_source,
    feature_coverage,
)
from app.knowledge.neighbor_eligibility import check_neighbor_eligibility
from app.search import search_utils

if TYPE_CHECKING:
    from app.data_structures import BugLocation
    from app.search.search_backend import SearchBackend


@dataclass
class LintFinding:
    rule_id: str
    layer: str
    severity: str  # warn | block
    remediation: str


def _normalize_method_key(class_name: str | None, method_name: str | None) -> str:
    return f"{class_name or ''}::{method_name or ''}"


def _scan_needs_fix_rows(sibling_scan: list[dict]) -> list[dict]:
    return [r for r in sibling_scan if str(r.get("needs_fix", "")).lower() == "yes"]


def _location_keys(bug_locations_raw: list[dict]) -> set[str]:
    keys: set[str] = set()
    for loc in bug_locations_raw:
        keys.add(
            _normalize_method_key(loc.get("class"), loc.get("method") or loc.get("method_name"))
        )
    return keys


def _parent_body_complexity(backend: SearchBackend, class_name: str, method_name: str) -> int:
    """Heuristic: non-trivial parent implementation line count."""
    for ancestor in backend.class_relation_index.get(class_name, []):
        funcs = backend.class_func_index.get(ancestor, {})
        if method_name not in funcs:
            continue
        for fname, (start, end) in funcs[method_name]:
            try:
                body = search_utils.get_code_snippets(fname, start, end)
                return len(body.splitlines())
            except Exception:
                return 0
    return 0


def lint_localization(
    backend: SearchBackend,
    *,
    sibling_scan: list[dict],
    bug_locations_raw: list[dict],
    bug_locs: list[BugLocation],
    issue_text: str,
    project_path: str,
) -> list[LintFinding]:
    if not config.enable_sympy_pipeline_v2:
        return []

    findings: list[LintFinding] = []

    # L1: IB_SCAN_EMPTY_WITH_LOCATIONS
    if bug_locations_raw and not sibling_scan:
        findings.append(
            LintFinding(
                "IB_SCAN_EMPTY_WITH_LOCATIONS",
                "L1_structural",
                "block",
                "bug_locations require sibling_scan table first",
            )
        )

    # L1: IB_SCAN_COVERAGE_MISMATCH
    needs_fix_rows = _scan_needs_fix_rows(sibling_scan)
    loc_keys = _location_keys(bug_locations_raw)
    for row in needs_fix_rows:
        key = _normalize_method_key(row.get("class"), row.get("method_or_handler"))
        if key not in loc_keys:
            findings.append(
                LintFinding(
                    "IB_SCAN_COVERAGE_MISMATCH",
                    "L1_structural",
                    "block",
                    f"needs_fix=yes row {row.get('method_or_handler')} missing from bug_locations",
                )
            )

    # L1: IB_SCOPE_PROOF_MISSING
    for row in sibling_scan:
        if str(row.get("needs_fix", "")).lower() == "no":
            proof = (row.get("scope_proof") or "").strip()
            if not proof:
                findings.append(
                    LintFinding(
                        "IB_SCOPE_PROOF_MISSING",
                        "L1_structural",
                        "block",
                        f"needs_fix=no for {row.get('method_or_handler')} requires scope_proof",
                    )
                )

    issue_fs = extract_from_issue(issue_text)

    for loc in bug_locations_raw:
        spec_source = loc.get("spec_source", "")
        spec_rationale = (loc.get("spec_rationale") or "").strip()
        neighbor_ref = loc.get("neighbor_reference", "")
        target_class = loc.get("class", "")
        target_method = loc.get("method", "")
        ib_text = loc.get("intended_behavior", "")
        ib_fs = extract_from_intended_behavior(ib_text)

        if not spec_source or not spec_rationale:
            findings.append(
                LintFinding(
                    "IB_SPEC_METADATA_MISSING",
                    "L1_structural",
                    "block",
                    f"spec_source and spec_rationale required for {target_method}",
                )
            )

        # L1: IB_PARENT_OVERRIDE_UNPROVEN
        if target_class and target_method:
            parent_lines = _parent_body_complexity(backend, target_class, target_method)
            if parent_lines > 15:
                scan_proof = any(
                    (r.get("method_or_handler") == target_method and r.get("scope_proof"))
                    for r in sibling_scan
                )
                if not scan_proof:
                    findings.append(
                        LintFinding(
                            "IB_PARENT_OVERRIDE_UNPROVEN",
                            "L1_structural",
                            "block",
                            f"override of non-trivial parent {target_method} requires scope_proof in scan",
                        )
                    )

        if not neighbor_ref:
            if spec_source == "neighbor_contract":
                findings.append(
                    LintFinding(
                        "IB_NEIGHBOR_REFERENCE_MISSING",
                        "L1_structural",
                        "block",
                        "neighbor_reference required when spec_source=neighbor_contract",
                    )
                )
            continue

        elig = check_neighbor_eligibility(
            backend,
            target_class=target_class,
            target_method=target_method,
            neighbor_reference=neighbor_ref,
            sibling_scan=sibling_scan,
        )

        if not elig.eligible:
            findings.append(
                LintFinding(
                    "IB_NEIGHBOR_ELIGIBILITY_FAIL",
                    "L2_evidence",
                    "warn",
                    elig.reason,
                )
            )
            continue

        # L2: extract neighbor features from source
        neighbor_fs = None
        if target_class in backend.class_func_index:
            if neighbor_ref in backend.class_func_index.get(target_class, {}):
                for fname, (start, end) in backend.class_func_index[target_class][neighbor_ref]:
                    try:
                        src = search_utils.get_code_snippets(fname, start, end)
                        neighbor_fs = extract_from_source(src, neighbor_ref)
                    except Exception:
                        pass
                    break

        if neighbor_fs:
            cov = feature_coverage(ib_fs, neighbor_fs)
            if cov < FEATURE_COVERAGE_MIN and spec_source != "issue_example":
                findings.append(
                    LintFinding(
                        "IB_NEIGHBOR_FEATURE_COVERAGE_LOW",
                        "L2_evidence",
                        "warn",
                        f"IB feature coverage {cov:.2f} < {FEATURE_COVERAGE_MIN} vs neighbor {neighbor_ref}",
                    )
                )

            if contracts_conflict(issue_fs, neighbor_fs, ib_fs):
                findings.append(
                    LintFinding(
                        "IB_ISSUE_NEIGHBOR_CONFLICT",
                        "L2_evidence",
                        "block",
                        f"intended_behavior follows Issue but conflicts with eligible neighbor {neighbor_ref}",
                    )
                )

    return findings


def has_blocking_findings(findings: list[LintFinding]) -> bool:
    return any(f.severity == "block" for f in findings)


def write_validation_report(output_dir: str, findings: list[LintFinding]) -> None:
    path = Path(output_dir) / "bug_locations_validation.json"
    payload = [
        {
            "rule_id": f.rule_id,
            "layer": f.layer,
            "severity": f.severity,
            "remediation": f.remediation,
        }
        for f in findings
    ]
    path.write_text(json.dumps(payload, indent=2))


def format_rewrite_message(findings: list[LintFinding]) -> str:
    blocks = ["intended_behavior rejected by mechanical linter:"]
    for f in findings:
        if f.severity == "block":
            blocks.append(f"- {f.rule_id}: {f.remediation}")
    blocks.append("Rewrite bug_locations and sibling_scan per LOCALIZATION_INTENDED_BEHAVIOR_CONTRACT.")
    return "\n".join(blocks)
