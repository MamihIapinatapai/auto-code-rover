"""
Sibling scan mechanical validation (HB).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from app import config
from app.search import search_utils

if TYPE_CHECKING:
    from app.search.search_backend import SearchBackend


@dataclass
class ScanFinding:
    rule_id: str
    severity: str  # warn | block
    remediation: str
    row_index: int | None = None


def _resolve_method(
    backend: SearchBackend, row: dict
) -> tuple[str | None, str | None]:
    method = row.get("method_or_handler", "")
    class_name = row.get("class", "")
    file_path = row.get("file", "")
    if not method:
        return None, None

    if class_name and class_name in backend.class_func_index:
        if method in backend.class_func_index[class_name]:
            return class_name, method

    for cls, funcs in backend.class_func_index.items():
        if method in funcs:
            if not class_name or cls == class_name:
                return cls, method

    return class_name or None, method


def validate_sibling_scan(
    backend: SearchBackend,
    sibling_scan: list[dict],
    *,
    project_path: str = "",
) -> list[ScanFinding]:
    if not config.enable_sympy_pipeline_v2:
        return []

    findings: list[ScanFinding] = []
    for idx, row in enumerate(sibling_scan):
        if not isinstance(row, dict):
            findings.append(
                ScanFinding(
                    "SCAN_ROW_INVALID",
                    "block",
                    "Each sibling_scan row must be an object",
                    idx,
                )
            )
            continue

        cls, method = _resolve_method(backend, row)
        found = False
        if method and cls and cls in backend.class_func_index:
            found = method in backend.class_func_index[cls]
        if not found:
            for c, funcs in backend.class_func_index.items():
                if method and method in funcs:
                    found = True
                    break
        if not method or not found:
            findings.append(
                ScanFinding(
                    "SCAN_ROW_NOT_FOUND",
                    "block",
                    f"method_or_handler '{row.get('method_or_handler')}' not found in class index",
                    idx,
                )
            )
            continue

        evidence = row.get("evidence_snippet", "")
        line_range = row.get("evidence_line_range")
        file_path = row.get("file", "")
        if evidence and file_path and line_range and len(line_range) >= 2:
            try:
                abs_path = file_path
                if project_path and not Path(file_path).is_absolute():
                    abs_path = str(Path(project_path) / file_path)
                snippet = search_utils.get_code_snippets(
                    abs_path, int(line_range[0]), int(line_range[1])
                )
                if evidence not in snippet:
                    findings.append(
                        ScanFinding(
                            "SCAN_EVIDENCE_MISMATCH",
                            "warn",
                            f"evidence_snippet not found in source for {method}",
                            idx,
                        )
                    )
            except Exception:
                findings.append(
                    ScanFinding(
                        "SCAN_EVIDENCE_MISMATCH",
                        "warn",
                        f"could not verify evidence_snippet for {method}",
                        idx,
                    )
                )

    return findings


def enrich_scan_suggestions(
    backend: SearchBackend,
    class_name: str,
    sibling_scan: list[dict],
    output_dir: str | None,
) -> list[dict]:
    """P2: suggest CO_FIX rows from same-class method listing (warn only)."""
    if not config.enable_sympy_pipeline_v2 or not class_name:
        return []
    if class_name not in backend.class_func_index:
        return []

    scanned = {r.get("method_or_handler") for r in sibling_scan}
    suggestions = []
    for method in backend.class_func_index[class_name]:
        if method in scanned:
            continue
        if method.startswith("_eval_is_") or method.startswith("_print_"):
            suggestions.append(
                {
                    "method_or_handler": method,
                    "class": class_name,
                    "anti_pattern_id": "SCAN_SUGGEST_REVIEW",
                    "needs_fix": "unknown",
                    "machine_suggested": True,
                    "note": "Same-class handler not in scan table — review for CO_FIX",
                }
            )

    if suggestions and output_dir:
        path = Path(output_dir) / "scan_suggestions.json"
        path.write_text(json.dumps(suggestions, indent=2))

    return suggestions
