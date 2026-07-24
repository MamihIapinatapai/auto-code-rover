"""Machine heuristics for Issue↔AC layer / assertion strength (v3.3)."""

from __future__ import annotations

import re
from typing import Any

from app.spec_parser.ac_markers import extract_ac_section_body, parse_ac_sections


_CLI_HINT_RE = re.compile(r"\b(cli|command|click|argparse|subcommand)\b", re.I)
_WEB_HINT_RE = re.compile(r"\b(web|http|/api/|endpoint|testclient|flask|starlette)\b", re.I)
_CLI_EVIDENCE_RE = re.compile(r"\b(CliRunner|subprocess\.|click\.|invoke\()", re.I)
_WEB_EVIDENCE_RE = re.compile(
    r"\b(TestClient|httpx\.|requests\.|client\.(get|post|put|delete))\b", re.I
)


def check_layer_mismatch(script: str, must_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Return warning dicts for WRONG_LAYER_CLI / WRONG_LAYER_WEB (non-blocking)."""
    section_map = parse_ac_sections(script, must_ids or [])
    warnings: list[dict[str, Any]] = []
    for ac_id in section_map.found:
        body = extract_ac_section_body(script, ac_id) or ""
        # Include the marker comment line for title hints
        header = ""
        for line in script.splitlines():
            if f"# --- {ac_id}" in line:
                header = line
                break
        blob = header + "\n" + body
        if _CLI_HINT_RE.search(blob) and not _CLI_EVIDENCE_RE.search(body):
            warnings.append(
                {
                    "code": "WRONG_LAYER_CLI",
                    "ac_id": ac_id,
                    "detail": "AC mentions CLI/command but body lacks CliRunner/subprocess/click",
                }
            )
        if _WEB_HINT_RE.search(blob) and not _WEB_EVIDENCE_RE.search(body):
            warnings.append(
                {
                    "code": "WRONG_LAYER_WEB",
                    "ac_id": ac_id,
                    "detail": "AC mentions Web/HTTP but body lacks TestClient/httpx/requests",
                }
            )
    return warnings


def run_coverage_heuristics(
    script: str,
    *,
    must_ids: list[str] | None = None,
    layer_hints: dict[str, str] | None = None,
    entrypoint_names: list[str] | None = None,
) -> dict[str, Any]:
    mismatches = check_layer_mismatch(script, must_ids)
    # If Anchor says CLI present but script ignores entry names / CliRunner → keep warning
    hints = layer_hints or {}
    names = [n.lower() for n in (entrypoint_names or []) if n]
    script_l = (script or "").lower()
    if hints.get("cli") == "present":
        has_cli_ex = bool(
            re.search(r"\b(clirunner|subprocess\.|click\.)\b", script_l)
            or any(n in script_l for n in names)
        )
        if not has_cli_ex and not any(w["code"] == "WRONG_LAYER_CLI" for w in mismatches):
            mismatches.append(
                {
                    "code": "WRONG_LAYER_CLI",
                    "ac_id": "*",
                    "detail": "Anchor layer_hints.cli=present but script lacks CliRunner/entrypoint use",
                }
            )
    return {
        "wrong_layer_count": len(mismatches),
        "warnings": mismatches,
    }
