"""Contract-path orchestration helpers (fill → BC → render → SCC)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger

from app import config
from app.data_structures import MessageThread
from app.model import common as model_common
from app.spec_parser.behavior_contract import (
    empty_contract,
    parse_contract_json,
    sanitize_contract_for_mvp,
    validate_contract,
)
from app.spec_parser.behavior_skeleton import RenderResult, render_s1_script
from app.spec_parser.contract_fill_prompts import (
    CONTRACT_FILL_SYSTEM,
    format_contract_fill_user,
)
from app.spec_parser.contract_repair_prompts import (
    CONTRACT_REPAIR_SYSTEM,
    format_contract_repair_user,
)
from app.spec_parser.dual_state_lite import check_dsl_rules
from app.spec_parser.recipe_loader import (
    format_recipe_hints_for_prompt,
    load_recipe_cards,
    match_recipe_hints,
)
from app.spec_parser.contract_llm_review import (
    review_contract_semantics,
    review_to_feedback,
)
from app.spec_parser.script_contract_align import run_scc_llm, run_scc_machine
from app.spec_parser.table_gen_feedback import apply_items_patch, empty_feedback, merge_feedback
from app.spec_parser.usage_miner import format_usage_for_prompt, mine_usage


def _safe_render(
    contract: dict[str, Any],
    cards: dict,
    usage_snippets: dict | list | None = None,
) -> tuple[str, str | None]:
    """Return (script, reason_code). reason_code set when render blocked."""
    res = render_s1_script(
        contract, recipe_cards=cards, usage_snippets=usage_snippets
    )
    if isinstance(res, RenderResult):
        if not res.ok:
            return "", res.reason_code or "render_blocked"
        return res.script or "", None
    return str(res or ""), None


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            raise
        return json.loads(m.group(0))


def llm_fill_contract(
    *,
    issue_text: str,
    anchor_summary: str = "",
    use_llm: bool = True,
) -> tuple[dict[str, Any], MessageThread]:
    cards = match_recipe_hints(issue_text, anchor_summary)
    hints = format_recipe_hints_for_prompt(cards)
    thread = MessageThread()
    thread.add_system(CONTRACT_FILL_SYSTEM)
    thread.add_user(
        format_contract_fill_user(
            issue_text=issue_text,
            anchor_summary=anchor_summary,
            recipe_hints=hints,
        )
    )
    if not use_llm:
        # Deterministic degraded S1 stub for offline tests
        quote = issue_text.strip()[:120] or "feature must work"
        contract = empty_contract()
        contract["degraded"] = True
        contract["items"] = [
            {
                "must_id": "M1-s1",
                "issue_quote": quote if quote in issue_text else issue_text[:80],
                "layer": "lib",
                "call_graph": ["feature_api", "run"],
                "inputs": {},
                "oracle_kind": "raises",
                "expect": {"oracle_kind": "raises", "exception": "AssertionError"},
                "fail_mode": "not_implemented",
                "recipe_id": cards[0]["id"] if cards else None,
                "expect_confidence": "low",
                "tier": "S1",
            }
        ]
        # ensure quote is substring
        if contract["items"][0]["issue_quote"] not in issue_text and issue_text:
            contract["items"][0]["issue_quote"] = issue_text[: min(80, len(issue_text))]
        return contract, thread

    response, *_ = model_common.SELECTED_MODEL.call(
        thread.to_msg(), response_format="json_object"
    )
    thread.add_model(response)
    data = _extract_json(response)
    contract = sanitize_contract_for_mvp(
        parse_contract_json(data), issue_text=issue_text
    )
    # Auto-attach recipe_id when single hint
    if cards and contract.get("items"):
        for it in contract["items"]:
            if not it.get("recipe_id"):
                it["recipe_id"] = cards[0].get("id")
    return contract, thread


def llm_repair_contract(
    *,
    contract: dict[str, Any],
    feedback: dict[str, Any],
    issue_text: str,
    use_llm: bool = True,
) -> tuple[dict[str, Any], MessageThread]:
    thread = MessageThread()
    thread.add_system(CONTRACT_REPAIR_SYSTEM)
    # format_contract_repair_user may have specific signature — fall back
    try:
        user = format_contract_repair_user(
            issue_text=issue_text,
            contract_json=contract,
            table_gen_feedback=feedback,
        )
    except TypeError:
        user = (
            f"## Issue\n{issue_text}\n\n## Contract\n"
            f"{json.dumps(contract, indent=2)}\n\n## Feedback\n"
            f"{json.dumps(feedback, indent=2)}\n"
        )
    thread.add_user(user)
    if not use_llm:
        return contract, thread
    response, *_ = model_common.SELECTED_MODEL.call(
        thread.to_msg(), response_format="json_object"
    )
    thread.add_model(response)
    repair = _extract_json(response)
    cards = load_recipe_cards()
    updated, report = apply_items_patch(
        contract, repair, issue_text=issue_text, recipe_cards=cards
    )
    if not report.get("ok"):
        # try treating repair as full contract
        try:
            cand = sanitize_contract_for_mvp(
                parse_contract_json(repair), issue_text=issue_text
            )
            v = validate_contract(cand, issue_text=issue_text, recipe_cards=cards)
            if v["passed"]:
                return cand, thread
        except Exception:  # noqa: BLE001
            pass
        logger.warning("contract repair apply rolled back: {}", report)
        # still return sanitized original to allow progress
        return sanitize_contract_for_mvp(contract, issue_text=issue_text), thread
    return sanitize_contract_for_mvp(updated, issue_text=issue_text), thread


def run_contract_pipeline(
    *,
    output_dir: Path,
    issue_text: str,
    anchor_summary: str = "",
    decision=None,
    use_llm: bool = True,
    issue_kind: str = "FEATURE",
    task_id: str = "",
    project_path: str = "",
) -> dict[str, Any]:
    """Execute S_FILL → S_BC → (LLM review) → S_RENDER → S_SCC_M → (SCC-L).

    Returns dict with keys: ok, contract, script, scc, bc_validate, budget_left, reason
    """
    output_dir = Path(output_dir)
    cards = load_recipe_cards()
    budget = int(getattr(config, "spec_parser_contract_max_expect_retries", 2) or 2)
    rerender_budget = 1
    last_table_review: dict[str, Any] | None = None
    usage_snippets: dict[str, Any] = {
        "snippets": [],
        "sufficiency": "insufficient",
        "summary_for_prompt": "(none)",
    }
    if getattr(config, "spec_parser_enable_usage_miner", False):
        try:
            repo_guess = Path(project_path) if project_path else output_dir
            if not project_path:
                for _ in range(4):
                    if (repo_guess / "pyproject.toml").exists() or (
                        repo_guess / "setup.py"
                    ).exists():
                        break
                    if repo_guess.parent == repo_guess:
                        break
                    repo_guess = repo_guess.parent
            usage_snippets = mine_usage(
                repo_guess,
                issue_text,
                recipe_cards=cards,
                budget_files=int(
                    getattr(config, "spec_parser_usage_mine_budget_files", 80) or 80
                ),
                allow_tests=bool(
                    getattr(config, "spec_parser_usage_mine_tests_call_shape", True)
                ),
            )
            (output_dir / "usage_snippets.json").write_text(
                json.dumps(usage_snippets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("usage_miner failed: {}", e)

    if decision:
        decision.record(
            node_id="D_contract_step1",
            round_no=0,
            options=["fill", "skip"],
            decision="fill",
            reason="stub_triggered_contract_path",
            policy_id="contract_path_v34",
            action="fill",
        )

    contract, fill_thread = llm_fill_contract(
        issue_text=issue_text,
        anchor_summary=anchor_summary,
        use_llm=use_llm,
    )
    contract = sanitize_contract_for_mvp(contract, issue_text=issue_text)
    contract.setdefault("issue_kind", issue_kind)
    (output_dir / "contract_fill_thread.json").write_text(
        json.dumps({"note": "fill completed"}, indent=2)
    )
    try:
        fill_thread.save_to_file(str(output_dir / "contract_fill_messages.json"))
    except Exception:  # noqa: BLE001
        pass

    for attempt in range(budget + 2):
        bc = validate_contract(contract, issue_text=issue_text, recipe_cards=cards)
        (output_dir / "bc_validate.json").write_text(json.dumps(bc, indent=2))
        if decision:
            decision.record(
                node_id="D_contract_bc_validate",
                round_no=attempt,
                options=["pass", "blocking"],
                decision="pass" if bc["passed"] else "blocking",
                reason=str(bc.get("blocking")[:2]),
                policy_id="validate_contract_v34",
                action="render" if bc["passed"] else "repair",
            )
        if not bc["passed"]:
            # Always sanitize once more before repair/budget burn
            contract = sanitize_contract_for_mvp(contract, issue_text=issue_text)
            bc = validate_contract(contract, issue_text=issue_text, recipe_cards=cards)
            (output_dir / "bc_validate.json").write_text(json.dumps(bc, indent=2))
            if bc["passed"]:
                continue
            if budget <= 0:
                # Last resort: keep a single degraded raises S1 row
                quote = (issue_text or "feature")[:120]
                if issue_text and quote not in issue_text:
                    quote = issue_text[: min(80, len(issue_text))]
                contract = empty_contract(issue_kind=issue_kind)
                contract["degraded"] = True
                contract["degraded_reason"] = "bc_budget_exhausted_fallback"
                contract["items"] = [
                    {
                        "must_id": "M1-s1-fallback",
                        "issue_quote": quote,
                        "layer": "lib",
                        "call_graph": ["feature_api", "run"],
                        "inputs": {},
                        "oracle_kind": "raises",
                        "expect": {
                            "oracle_kind": "raises",
                            "exception": "AssertionError",
                        },
                        "fail_mode": "not_implemented",
                        "recipe_id": None,
                        "expect_confidence": "low",
                        "tier": "S1",
                    }
                ]
                bc = validate_contract(
                    contract, issue_text=issue_text, recipe_cards=cards
                )
                if not bc["passed"]:
                    return {
                        "ok": False,
                        "contract": contract,
                        "script": "",
                        "reason": "bc_blocking_budget_exhausted",
                        "bc_validate": bc,
                        "scc": None,
                        "budget_left": budget,
                    }
                # fall through to render with fallback contract
                script, _render_err = _safe_render(contract, cards, usage_snippets)
                (output_dir / "behavior_contract.json").write_text(
                    json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                if _render_err or not script:
                    return {
                        "ok": False,
                        "contract": contract,
                        "script": "",
                        "reason": f"render_blocked:{_render_err or 'empty'}",
                        "bc_validate": bc,
                        "scc": None,
                        "budget_left": budget,
                        "render_blocked": True,
                    }
                (output_dir / "test_feature.py").write_text(script, encoding="utf-8")
                return {
                    "ok": True,
                    "contract": contract,
                    "script": script,
                    "reason": "degraded_fallback",
                    "bc_validate": bc,
                    "scc": {"scc_m_pass": False, "blocking": False, "findings": []},
                    "budget_left": budget,
                    "tier": "S1",
                    "degraded": True,
                }
            feedback = empty_feedback(source="table_review")
            feedback["blocking"] = True
            feedback["summary_for_filler"] = "BC blocking; repair expect slots only"
            feedback["items"] = [
                {
                    "must_id": b.get("must_id") or "",
                    "error_type": "false_fail"
                    if "BC-09" in b.get("rule_id", "")
                    else "weak_degraded",
                    "severity": "blocking",
                    "what_is_wrong": b.get("msg", ""),
                    "allowed_edits": ["expect", "fail_mode", "expect_confidence"],
                    "forbidden_edits": ["call_graph", "recipe_id", "layer", "entrypoint"],
                }
                for b in bc["blocking"]
            ]
            contract, _ = llm_repair_contract(
                contract=contract,
                feedback=feedback,
                issue_text=issue_text,
                use_llm=use_llm,
            )
            budget -= 1
            if decision:
                decision.record(
                    node_id="D_contract_patch_apply",
                    round_no=attempt,
                    options=["applied", "rollback"],
                    decision="applied",
                    reason=f"budget_left={budget}",
                    policy_id="repair_v34",
                    action="revalidate",
                )
            continue

        # Optional table LLM semantic review (after BC pass, before render)
        table_review = review_contract_semantics(
            contract=contract,
            issue_text=issue_text,
            anchor_summary=anchor_summary,
            task_id=task_id,
            use_llm=use_llm,
        )
        last_table_review = table_review
        (output_dir / "contract_llm_review.json").write_text(
            json.dumps(table_review, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        contract["llm_review"] = {
            "verdict": table_review.get("verdict"),
            "blocking": table_review.get("blocking"),
            "triggered": table_review.get("triggered"),
            "summary": table_review.get("summary"),
            "trigger_reasons": table_review.get("trigger_reasons"),
        }
        if decision:
            decision.record(
                node_id="D_contract_llm_review",
                round_no=attempt,
                options=["pass", "warning", "revise", "reject", "skipped"],
                decision=str(table_review.get("verdict") or "skipped"),
                reason=str(table_review.get("summary") or "")[:120],
                policy_id="contract_llm_review_v34",
                action=(
                    "repair"
                    if table_review.get("verdict")
                    in {
                        "revise_expect",
                        "reject_false_fail",
                        "reject_off_must",
                    }
                    else "render"
                ),
            )
        if table_review.get("verdict") in {
            "revise_expect",
            "reject_false_fail",
            "reject_off_must",
        }:
            if budget <= 0:
                # Do not abort the whole contract path: render last BC-valid contract
                # with an exhausted-review warning (ablation-friendly).
                if decision:
                    decision.record(
                        node_id="D_contract_llm_review",
                        round_no=attempt,
                        options=["abort", "render_anyway"],
                        decision="render_anyway",
                        reason="table_llm_budget_exhausted",
                        policy_id="contract_llm_review_v34",
                        action="render",
                    )
                contract["llm_review"] = {
                    **(contract.get("llm_review") or {}),
                    "budget_exhausted": True,
                    "render_anyway": True,
                }
                # fall through to render below
            else:
                fb = review_to_feedback(table_review)
                contract, _ = llm_repair_contract(
                    contract=contract,
                    feedback=fb,
                    issue_text=issue_text,
                    use_llm=use_llm,
                )
                budget -= 1
                if decision:
                    decision.record(
                        node_id="D_contract_patch_apply",
                        round_no=attempt,
                        options=["applied", "rollback"],
                        decision="applied",
                        reason=f"from_table_llm budget_left={budget}",
                        policy_id="repair_v34",
                        action="revalidate",
                    )
                continue

        script, _render_err = _safe_render(contract, cards, usage_snippets)
        if _render_err or not script.strip():
            (output_dir / "behavior_contract.json").write_text(
                json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if decision:
                decision.record(
                    node_id="D_contract_render",
                    round_no=attempt,
                    options=["ok", "error"],
                    decision="error",
                    reason=_render_err or "empty",
                    policy_id="render_s1_v35",
                    action="render_blocked",
                )
            return {
                "ok": False,
                "contract": contract,
                "script": "",
                "reason": f"render_blocked:{_render_err or 'empty'}",
                "bc_validate": bc,
                "scc": None,
                "budget_left": budget,
                "render_blocked": True,
                "usage_snippets": usage_snippets,
            }
        if decision:
            decision.record(
                node_id="D_contract_render",
                round_no=attempt,
                options=["ok", "error"],
                decision="ok",
                reason=f"bytes={len(script)}",
                policy_id="render_s1_v35",
                action="lint_scc",
            )

        if getattr(config, "spec_parser_enable_dual_state_lite", True):
            dsl = check_dsl_rules(script, contract=contract, issue_text=issue_text)
            (output_dir / "dual_state_lite.json").write_text(json.dumps(dsl, indent=2))
            if not dsl["passed"]:
                # force async template if DSL-01
                if any(x.get("rule_id") == "DSL-01" for x in dsl["blocking"]):
                    for it in contract.get("items") or []:
                        if it.get("layer") == "async":
                            it["needs_async_harness"] = True
                    script, _render_err = _safe_render(contract, cards, usage_snippets)
                    dsl = check_dsl_rules(script, contract=contract, issue_text=issue_text)
                if not dsl["passed"] and budget > 0:
                    budget -= 1
                    continue

        scc = {"scc_m_pass": True, "blocking": False, "findings": []}
        if getattr(config, "spec_parser_enable_script_contract_align", True):
            scc = run_scc_machine(contract, script, issue_text=issue_text)
            (output_dir / "scc_report.json").write_text(json.dumps(scc, indent=2))
            if decision:
                decision.record(
                    node_id="D_scc_machine",
                    round_no=attempt,
                    options=["pass", "render_error", "contract_error"],
                    decision=(
                        "pass"
                        if scc.get("scc_m_pass")
                        else scc.get("verdict", "contract_error")
                    ),
                    reason=scc.get("summary", ""),
                    policy_id="scc_m_v34",
                    action="sandbox" if scc.get("scc_m_pass") else "fix",
                )
            if scc.get("blocking"):
                if scc.get("verdict") == "render_error" and rerender_budget > 0:
                    rerender_budget -= 1
                    script, _render_err = _safe_render(contract, cards, usage_snippets)
                    scc = run_scc_machine(contract, script, issue_text=issue_text)
                    if scc.get("scc_m_pass"):
                        # fall through to SCC-L below
                        pass
                    else:
                        if budget <= 0:
                            return {
                                "ok": False,
                                "contract": contract,
                                "script": script,
                                "reason": "scc_blocking_budget_exhausted",
                                "bc_validate": bc,
                                "scc": scc,
                                "budget_left": budget,
                            }
                        fb = merge_feedback(
                            None,
                            {
                                "blocking": True,
                                "items": [
                                    {
                                        "must_id": f.get("must_id"),
                                        "error_type": "script_contract_mismatch",
                                        "severity": "blocking",
                                        "what_is_wrong": f.get("problem"),
                                        "allowed_edits": [
                                            "expect",
                                            "fail_mode",
                                            "expect_confidence",
                                        ],
                                }
                                    for f in scc.get("findings") or []
                                    if (f.get("patch") or {}).get("action")
                                    not in ("noop_rerender", "mark_render_bug")
                                ],
                            },
                        )
                        if fb["items"]:
                            contract, _ = llm_repair_contract(
                                contract=contract,
                                feedback=fb,
                                issue_text=issue_text,
                                use_llm=use_llm,
                            )
                            budget -= 1
                            continue
                        script, _render_err = _safe_render(contract, cards, usage_snippets)
                        scc = run_scc_machine(contract, script, issue_text=issue_text)
                        if not scc.get("scc_m_pass"):
                            if budget <= 0:
                                return {
                                    "ok": False,
                                    "contract": contract,
                                    "script": script,
                                    "reason": "scc_still_blocking",
                                    "bc_validate": bc,
                                    "scc": scc,
                                    "budget_left": budget,
                                }
                            budget -= 1
                            continue
                elif budget <= 0:
                    return {
                        "ok": False,
                        "contract": contract,
                        "script": script,
                        "reason": "scc_blocking_budget_exhausted",
                        "bc_validate": bc,
                        "scc": scc,
                        "budget_left": budget,
                    }
                else:
                    fb = merge_feedback(
                        None,
                        {
                            "blocking": True,
                            "items": [
                                {
                                    "must_id": f.get("must_id"),
                                    "error_type": "script_contract_mismatch",
                                    "severity": "blocking",
                                    "what_is_wrong": f.get("problem"),
                                    "allowed_edits": [
                                        "expect",
                                        "fail_mode",
                                        "expect_confidence",
                                    ],
                                }
                                for f in scc.get("findings") or []
                                if (f.get("patch") or {}).get("action")
                                not in ("noop_rerender", "mark_render_bug")
                            ],
                        },
                    )
                    if fb["items"]:
                        contract, _ = llm_repair_contract(
                            contract=contract,
                            feedback=fb,
                            issue_text=issue_text,
                            use_llm=use_llm,
                        )
                        budget -= 1
                        continue
                    script, _render_err = _safe_render(contract, cards, usage_snippets)
                    scc = run_scc_machine(contract, script, issue_text=issue_text)
                    if not scc.get("scc_m_pass"):
                        budget -= 1
                        continue

            # SCC-L after SCC-M pass
            if scc.get("scc_m_pass", True):
                scc_l = run_scc_llm(
                    contract,
                    script,
                    scc,
                    issue_text=issue_text,
                    task_id=task_id,
                    use_llm=use_llm,
                )
                scc = {
                    **scc,
                    "scc_l": scc_l,
                    "scc_l_pass": scc_l.get("scc_l_pass", True),
                }
                (output_dir / "scc_report.json").write_text(
                    json.dumps(scc, indent=2, ensure_ascii=False)
                )
                if decision:
                    decision.record(
                        node_id="D_scc_llm",
                        round_no=attempt,
                        options=["pass", "warning", "patch_contract", "skipped"],
                        decision=str(scc_l.get("verdict") or "skipped"),
                        reason=str(scc_l.get("summary") or "")[:120],
                        policy_id="scc_l_v34",
                        action=(
                            "repair"
                            if scc_l.get("blocking")
                            else "sandbox"
                        ),
                    )
                if scc_l.get("blocking"):
                    if budget <= 0:
                        return {
                            "ok": False,
                            "contract": contract,
                            "script": script,
                            "reason": "scc_l_blocking_budget_exhausted",
                            "bc_validate": bc,
                            "scc": scc,
                            "budget_left": budget,
                            "table_review": last_table_review,
                        }
                    fb = merge_feedback(
                        None,
                        {
                            "blocking": True,
                            "items": [
                                {
                                    "must_id": f.get("must_id"),
                                    "error_type": "script_contract_mismatch",
                                    "severity": "blocking",
                                    "what_is_wrong": f.get("problem"),
                                    "allowed_edits": [
                                        "expect",
                                        "fail_mode",
                                        "expect_confidence",
                                    ],
                                }
                                for f in scc_l.get("findings") or []
                                if isinstance(f, dict)
                                and (f.get("patch") or {}).get("action")
                                == "patch_expect"
                            ],
                        },
                    )
                    if fb["items"]:
                        contract, _ = llm_repair_contract(
                            contract=contract,
                            feedback=fb,
                            issue_text=issue_text,
                            use_llm=use_llm,
                        )
                        budget -= 1
                        continue
                    if scc_l.get("verdict") == "render_error" and rerender_budget > 0:
                        rerender_budget -= 1
                        script, _render_err = _safe_render(contract, cards, usage_snippets)
                        continue
                    # non-patchable blocking → accept with warning marker
                    scc["scc_l_pass"] = False
        break

    (output_dir / "behavior_contract.json").write_text(
        json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / "test_feature.py").write_text(script, encoding="utf-8")
    return {
        "ok": True,
        "contract": contract,
        "script": script,
        "reason": "ok",
        "bc_validate": validate_contract(
            contract, issue_text=issue_text, recipe_cards=cards
        ),
        "scc": scc,
        "budget_left": budget,
        "tier": contract.get("script_tier") or "S1",
        "degraded": bool(contract.get("degraded")),
        "table_review": last_table_review,
    }
