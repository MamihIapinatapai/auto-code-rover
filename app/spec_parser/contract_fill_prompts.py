"""Prompts for initial BehaviorContract fill (Step1–3) — MVP v1.

Separate from ``contract_repair_prompts`` (repair-only after reviews).
"""

from __future__ import annotations

import json
from typing import Any

CONTRACT_FILL_SYSTEM = """
You are the BehaviorContract FILLER for AutoCodeRover Spec Parser v3.4 (MVP).

You create or complete structured BehaviorContract items from the Issue.
You do NOT write pytest. A Renderer will compile the table into tests later.

Fill rules:
1. Every item needs: must_id, issue_quote (<=200, verbatim Issue substring),
   layer (lib|cli|web|async), call_graph (>=1 product symbols), inputs (JSON object),
   oracle_kind, expect (full envelope), fail_mode, recipe_id (or null),
   expect_confidence (high|low), tier (S1 for MVP).
2. issue_quote MUST be copied from Issue text (substring). No paraphrasing.
3. expect MUST be concrete for the oracle_kind (equality/field_path/raises/...).
   No empty expect, no "should work", no existence-only.
4. Prefer Issue literals for expect.value. If none, use raises/attr_error with
   expect_confidence=low (degraded S1) — do not invent numbers.
5. If Recipe hints lock a pattern, set recipe_id and keep call_graph consistent
   with the hint; do not use forbidden patterns from hints.
6. Output ONE JSON object only (a BehaviorContract document or {items:[...]}).

Output schema (document):
{
  "schema_version": "bc-1",
  "issue_kind": "FEATURE|BUG_FIX",
  "script_tier": "S1",
  "degraded": false,
  "degraded_reason": null,
  "items": [ { /* BehaviorContractItem MVP fields */ } ]
}
""".strip()


CONTRACT_FILL_USER = """
Fill a BehaviorContract (S1 MVP) from the Issue. JSON only. No pytest.

## Issue text
{issue_text}

## Optional ScriptAnchor summary
{anchor_summary}

## Optional Recipe hints
{recipe_hints}

## Optional seed items / prior draft (may be empty)
{prior_contract_json}

## Constraints
- At least one S1 item with concrete expect.
- issue_quote must be verbatim from Issue.
- Prefer high confidence when literals exist.
""".strip()


def format_contract_fill_user(
    *,
    issue_text: str,
    anchor_summary: str = "",
    recipe_hints: str = "",
    prior_contract: dict[str, Any] | str | None = None,
) -> str:
    if isinstance(prior_contract, dict):
        prior = json.dumps(prior_contract, ensure_ascii=False, indent=2)
    elif prior_contract:
        prior = str(prior_contract)
    else:
        prior = "(none)"
    return CONTRACT_FILL_USER.format(
        issue_text=issue_text.strip() or "(empty issue)",
        anchor_summary=(anchor_summary or "").strip() or "(none)",
        recipe_hints=(recipe_hints or "").strip() or "(none)",
        prior_contract_json=prior,
    )
