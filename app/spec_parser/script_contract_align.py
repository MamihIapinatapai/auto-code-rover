"""Script↔Contract mechanical alignment (SCC-M) for v3.4."""

from __future__ import annotations

import re
from typing import Any

from app.spec_parser.behavior_contract import sanitize_must_id
from app.spec_parser.recipe_loader import load_recipe_cards, recipe_compliance

_PRIVATE_RE = re.compile(r"(?:from\s+\S+\s+import\s+\S*_|import\s+\S+\._|_\w+\._internal)")


def _ac_section(script: str, must_id: str) -> str:
    mid = sanitize_must_id(must_id)
    # Prefer comment anchor
    pat = re.compile(
        rf"#\s*---\s*AC-{re.escape(mid)}\s*---(.*?)(?=#\s*---\s*AC-|\Z)",
        re.S | re.I,
    )
    m = pat.search(script)
    if m:
        return m.group(0)
    # function name
    pat2 = re.compile(
        rf"def\s+test_ac_{re.escape(mid)}\s*\(.*?(?=\ndef\s+|\Z)",
        re.S,
    )
    m2 = pat2.search(script)
    return m2.group(0) if m2 else ""


def run_scc_machine(
    contract: dict[str, Any],
    script: str,
    *,
    issue_text: str = "",
) -> dict[str, Any]:
    findings: list[dict] = []
    cards = load_recipe_cards()

    for item in contract.get("items") or []:
        mid = str(item.get("must_id") or "")
        sec = _ac_section(script, mid)
        if not sec and f"test_ac_{sanitize_must_id(mid)}" not in script:
            findings.append(
                {
                    "finding_id": f"SCC01-{mid}",
                    "rule_id": "SCC-01",
                    "must_id": mid,
                    "channel": "machine",
                    "problem": "missing_ac_anchor",
                    "patch": {"action": "mark_render_bug", "path": "", "next_value": None},
                }
            )
            continue

        cg = item.get("call_graph") or []
        for sym in cg:
            token = str(sym).split(".")[-1]
            if token and token not in sec and str(sym) not in sec:
                findings.append(
                    {
                        "finding_id": f"SCC02-{mid}-{token}",
                        "rule_id": "SCC-02",
                        "must_id": mid,
                        "channel": "machine",
                        "problem": "call_graph_gap",
                        "patch": {
                            "action": "noop_rerender",
                            "path": "",
                            "next_value": None,
                        },
                    }
                )
                break

        kind = str(
            item.get("oracle_kind")
            or (item.get("expect") or {}).get("oracle_kind")
            or ""
        )
        exp = item.get("expect") or {}
        if kind in ("equality", "field_path", "contains"):
            val = exp.get("value")
            if val is not None:
                lit = repr(val)
                # Prefer exact literal form; avoid bare short-string false positives
                present = lit in sec
                if not present and not isinstance(val, str):
                    present = str(val) in sec
                if not present and isinstance(val, str) and len(val) >= 3:
                    present = val in sec
                if not present:
                    findings.append(
                        {
                            "finding_id": f"SCC03-{mid}",
                            "rule_id": "SCC-03",
                            "must_id": mid,
                            "channel": "machine",
                            "problem": "missing_expect_literal",
                            "patch": {
                                "action": "noop_rerender",
                                "path": f"items[must_id={mid}].expect.value",
                                "next_value": val,
                            },
                        }
                    )
        if kind == "raises" and "pytest.raises" not in sec and "raises(" not in sec:
            findings.append(
                {
                    "finding_id": f"SCC04-{mid}",
                    "rule_id": "SCC-04",
                    "must_id": mid,
                    "channel": "machine",
                    "problem": "missing_raises",
                    "patch": {"action": "noop_rerender", "path": "", "next_value": None},
                }
            )
        if kind == "http_status":
            if "status" not in sec.lower():
                findings.append(
                    {
                        "finding_id": f"SCC05-{mid}",
                        "rule_id": "SCC-05",
                        "must_id": mid,
                        "channel": "machine",
                        "problem": "missing_status_assert",
                        "patch": {"action": "noop_rerender", "path": "", "next_value": None},
                    }
                )
            ep = str(item.get("entrypoint") or "")
            if ep and ep not in sec:
                findings.append(
                    {
                        "finding_id": f"SCC05b-{mid}",
                        "rule_id": "SCC-05",
                        "must_id": mid,
                        "channel": "machine",
                        "problem": "missing_entrypoint_literal",
                        "patch": {"action": "noop_rerender", "path": "", "next_value": None},
                    }
                )

        # SCC-06 hasattr as main assert
        if re.search(r"assert\s+hasattr\s*\(", sec) or re.search(
            r"assert\s+.+\s+in\s+dir\s*\(", sec
        ):
            findings.append(
                {
                    "finding_id": f"SCC06-{mid}",
                    "rule_id": "SCC-06",
                    "must_id": mid,
                    "channel": "machine",
                    "problem": "existence_assert",
                    "patch": {"action": "mark_render_bug", "path": "", "next_value": None},
                }
            )

        # SCC-08 recipe source compliance
        rid = item.get("recipe_id")
        if rid and not recipe_compliance(sec or script, rid):
            findings.append(
                {
                    "finding_id": f"SCC08-{mid}",
                    "rule_id": "SCC-08",
                    "must_id": mid,
                    "channel": "machine",
                    "problem": "recipe_misaligned",
                    "patch": {"action": "noop_rerender", "path": "", "next_value": None},
                }
            )

        # SCC-09 private imports
        if _PRIVATE_RE.search(sec) or "_internal" in sec:
            # allow if Issue names it
            priv = True
            if issue_text and "_internal" in issue_text:
                priv = False
            if priv:
                findings.append(
                    {
                        "finding_id": f"SCC09-{mid}",
                        "rule_id": "SCC-09",
                        "must_id": mid,
                        "channel": "machine",
                        "problem": "private_api",
                        "patch": {"action": "mark_render_bug", "path": "", "next_value": None},
                    }
                )

    blocking = [
        f
        for f in findings
        if f.get("rule_id") in {
            "SCC-01",
            "SCC-02",
            "SCC-03",
            "SCC-04",
            "SCC-05",
            "SCC-06",
            "SCC-07",
            "SCC-08",
            "SCC-09",
        }
    ]
    # classify render_error vs contract_error
    render_only = all(
        (f.get("patch") or {}).get("action") in ("noop_rerender", "mark_render_bug")
        for f in blocking
    ) if blocking else True

    return {
        "verdict": "pass" if not blocking else ("render_error" if render_only else "patch_contract"),
        "blocking": bool(blocking),
        "findings": findings,
        "summary": f"{len(blocking)} blocking / {len(findings)} findings",
        "scc_m_pass": not blocking,
    }


_SCC_L_SYSTEM = """
You are SCC-L: Script↔Contract semantic aligner for Spec Parser v3.4.
SCC-M (mechanical) already passed. You only flag semantic residuals:
- expect direction vs issue_quote
- AC tests wrong Must
- stub/comment invoke without real product call
- recipe-aligned call_graph but wrong integration intent in script text

Output JSON only:
{
  "verdict": "pass|warning|patch_contract|render_error",
  "blocking": true|false,
  "findings": [
    {
      "finding_id": "SL1",
      "must_id": "...",
      "rule_id": "SCC-L-01",
      "channel": "llm",
      "problem": "short",
      "patch": {
        "action": "patch_expect|noop_rerender|mark_render_bug",
        "path": "items[must_id=...].expect",
        "next_value": null
      }
    }
  ],
  "summary": "<=200 chars"
}
Do not invent APIs. Prefer patch_expect over rewriting call_graph.
""".strip()


def should_run_scc_llm(
    contract: dict[str, Any],
    scc_m: dict[str, Any],
    *,
    issue_text: str = "",
    task_id: str = "",
) -> tuple[bool, list[str]]:
    from app import config
    from app.spec_parser.contract_llm_review import high_risk_reasons

    if not getattr(config, "spec_parser_enable_script_contract_llm", False):
        return False, []
    mode = str(
        getattr(config, "spec_parser_script_contract_llm_mode", "high_risk_only") or "off"
    ).lower()
    if mode in {"off", "false", "0", "no"}:
        return False, []
    if not scc_m.get("scc_m_pass", True):
        return False, ["scc_m_not_pass"]
    reasons = high_risk_reasons(contract, issue_text=issue_text, task_id=task_id)
    non_blocking = [
        f for f in (scc_m.get("findings") or []) if f not in (scc_m.get("blocking") and [])
    ]
    # any mechanical non-empty findings that were non-blocking
    if scc_m.get("findings") and not scc_m.get("blocking"):
        reasons = list(reasons) + ["scc_m_soft_findings"]
    # stub invoke heuristic in script is handled by caller via script text check
    if mode == "always":
        return True, reasons or ["mode=always"]
    if mode == "high_risk_only":
        return bool(reasons), reasons
    return False, []


def run_scc_llm(
    contract: dict[str, Any],
    script: str,
    scc_m: dict[str, Any],
    *,
    issue_text: str = "",
    task_id: str = "",
    use_llm: bool = True,
) -> dict[str, Any]:
    """Optional SCC-L after SCC-M pass."""
    from app import config
    from app.data_structures import MessageThread
    from app.model import common as model_common

    should, reasons = should_run_scc_llm(
        contract, scc_m, issue_text=issue_text, task_id=task_id
    )
    # also trigger if script looks like comment stub
    if (
        not should
        and getattr(config, "spec_parser_enable_script_contract_llm", False)
        and "result = None  # invoke" in (script or "")
    ):
        should = True
        reasons = list(reasons) + ["renderer_stub_invoke"]

    if not should:
        return {
            "verdict": "skipped",
            "blocking": False,
            "findings": [],
            "summary": "scc_l skipped",
            "scc_l_pass": True,
            "triggered": False,
            "trigger_reasons": reasons,
        }

    if not use_llm:
        return {
            "verdict": "pass",
            "blocking": False,
            "findings": [],
            "summary": "scc_l offline stub pass",
            "scc_l_pass": True,
            "triggered": True,
            "trigger_reasons": reasons,
        }

    import json

    thread = MessageThread()
    thread.add_system(_SCC_L_SYSTEM)
    thread.add_user(
        "Issue:\n"
        + (issue_text or "")[:6000]
        + "\n\nContract:\n"
        + json.dumps(contract, ensure_ascii=False)[:8000]
        + "\n\nScript:\n"
        + (script or "")[:8000]
        + "\n\nSCC-M summary:\n"
        + json.dumps(
            {
                "summary": scc_m.get("summary"),
                "findings": scc_m.get("findings") or [],
            },
            ensure_ascii=False,
        )[:2000]
        + "\n\nTrigger reasons: "
        + ", ".join(reasons)
    )
    try:
        response, *_ = model_common.SELECTED_MODEL.call(
            thread.to_msg(), response_format="json_object"
        )
        raw = json.loads(response) if response.strip().startswith("{") else None
        if raw is None:
            m = re.search(r"\{[\s\S]*\}", response)
            raw = json.loads(m.group(0)) if m else {}
    except Exception as e:  # noqa: BLE001
        return {
            "verdict": "warning",
            "blocking": False,
            "findings": [],
            "summary": f"scc_l failed: {e}",
            "scc_l_pass": True,
            "triggered": True,
            "trigger_reasons": reasons,
            "error": str(e),
        }

    if not isinstance(raw, dict):
        raw = {}
    verdict = str(raw.get("verdict") or "pass")
    if verdict not in {"pass", "warning", "patch_contract", "render_error"}:
        verdict = "warning"
    findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
    blocking = bool(raw.get("blocking")) and verdict in {
        "patch_contract",
        "render_error",
    }
    # Soft-fail: stub invoke always at least warning finding
    if "result = None  # invoke" in script and not any(
        "stub" in str(f.get("problem", "")).lower() for f in findings if isinstance(f, dict)
    ):
        findings = list(findings) + [
            {
                "finding_id": "SL-stub",
                "must_id": "",
                "rule_id": "SCC-L-STUB",
                "channel": "llm",
                "problem": "renderer_stub_invoke_comment",
                "patch": {
                    "action": "mark_render_bug",
                    "path": "",
                    "next_value": None,
                },
            }
        ]
        if verdict == "pass":
            verdict = "warning"
    return {
        "verdict": verdict,
        "blocking": blocking,
        "findings": findings,
        "summary": str(raw.get("summary") or "")[:200],
        "scc_l_pass": not blocking,
        "triggered": True,
        "trigger_reasons": reasons,
    }
