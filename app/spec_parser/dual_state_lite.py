"""Dual-State Lite heuristics (v3.4 WP-DSL)."""

from __future__ import annotations

import re
from typing import Any


def check_dsl_rules(
    script: str,
    *,
    contract: dict[str, Any] | None = None,
    issue_text: str = "",
) -> dict[str, Any]:
    """Return {blocking:[{rule_id,msg}], warnings, false_fail_risk_hits}."""
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if re.search(r"\brun_coroutine_threadsafe\b", script):
        if not re.search(r"\basyncio\.run\s*\(", script) and "get_running_loop" not in script:
            blocking.append(
                {
                    "rule_id": "DSL-01",
                    "msg": "run_coroutine_threadsafe without running loop evidence",
                }
            )

    # DSL-03 web Handler without entrypoint path literal
    if re.search(r"\b\w+Handler\b", script) and not re.search(
        r"[\"']/[A-Za-z0-9_\-/{}.]*[\"']", script
    ):
        blocking.append(
            {
                "rule_id": "DSL-03",
                "msg": "custom Handler name without real entrypoint path string",
            }
        )

    hits = len(blocking)
    # DSL-04: concrete expect coverage — scored externally; warn here if contract empty expects
    if contract:
        for item in contract.get("items") or []:
            exp = item.get("expect") or {}
            kind = item.get("oracle_kind") or exp.get("oracle_kind")
            if kind in ("equality", "field_path", "contains") and "value" not in exp:
                warnings.append(
                    {
                        "rule_id": "DSL-04",
                        "msg": f"item {item.get('must_id')} missing concrete expect",
                    }
                )

    return {
        "blocking": blocking,
        "warnings": warnings,
        "false_fail_risk_hits": hits,
        "passed": not blocking,
    }
