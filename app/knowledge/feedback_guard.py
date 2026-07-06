"""
Feedback guardrails for BC-ARCHITECTURE-ROLLBACK (§4.5).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app import config


def _load_artifact(artifact_path: str | None) -> dict | None:
    if not artifact_path or not Path(artifact_path).is_file():
        return None
    return json.loads(Path(artifact_path).read_text())


def guard_patch_feedback(
    review_advice: str,
    *,
    artifact_path: str | None,
    prev_patch_content: str | None = None,
) -> tuple[str, list[str]]:
    """
    Filter/augment reviewer patch advice before injection.
    Returns (filtered_advice, warnings).
    """
    if not config.enable_sympy_pipeline_v2:
        return review_advice, []

    warnings: list[str] = []
    advice = review_advice
    artifact = _load_artifact(artifact_path)

    if artifact:
        scan = artifact.get("sibling_scan", [])
        needs_fix_count = sum(
            1 for r in scan if str(r.get("needs_fix", "")).lower() == "yes"
        )
        if needs_fix_count > 1:
            only_one_patterns = [
                r"only\s+(fix|modify|change)\s+one",
                r"just\s+fix\s+the\s+one",
                r"single\s+location",
            ]
            for pat in only_one_patterns:
                if re.search(pat, advice, re.I):
                    warnings.append("FB_SCAN_CONTRADICTION")
                    advice += (
                        "\n\n[COUNTER-ADVICE] Scan table shows multiple needs_fix=yes "
                        "siblings — fix all CO_FIX rows per MINIMAL_COMPLETE_PATCH."
                    )
                    break

    if prev_patch_content and "self._print(" in prev_patch_content:
        inline_only = re.search(
            r"inline\s+(only|string|template|ternary)", advice, re.I
        )
        no_delegate = re.search(r"without\s+(delegat|self\._print)", advice, re.I)
        if inline_only or no_delegate:
            warnings.append("FB_DELEGATION_REGRESSION")
            advice += (
                "\n\n[COUNTER-ADVICE] Preserve AST Composition Delegation (self._print) "
                "from previous patch; add Prerequisite handlers if needed."
            )

    skip_sibling = re.search(r"skip\s+(other\s+)?sibling", advice, re.I)
    if skip_sibling:
        warnings.append("FB_RULE_CONTRADICTION")
        advice += (
            "\n\n[COUNTER-ADVICE] Do not skip siblings marked needs_fix=yes in scan table."
        )

    return advice, warnings
