"""BehaviorContract schema + validate_contract (Spec Parser v3.4)."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from app import config

ORACLE_KINDS = frozenset(
    {
        "equality",
        "field_path",
        "contains",
        "raises",
        "http_status",
        "stdout_regex",
        "attr_error",
    }
)
LAYERS = frozenset({"lib", "cli", "web", "async"})
_PROBE_ONLY = frozenset({"hasattr", "dir", "getattr", "hasattr", "vars", "type"})
_WEAK_VALUES = frozenset({"", "ok", "works", "true", "success", "pass"})


def _norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def normalize_quote_match(quote: str, issue_text: str) -> bool:
    """O7: whitespace-normalized substring."""
    q = _norm_ws(quote)
    issue = _norm_ws(issue_text)
    return bool(q) and q in issue


def sanitize_must_id(must_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", must_id or "M1").strip("_") or "M1"


def empty_contract(*, issue_kind: str = "FEATURE") -> dict[str, Any]:
    return {
        "schema_version": getattr(config, "spec_parser_contract_schema_version", "bc-1"),
        "issue_kind": issue_kind,
        "script_tier": "S1",
        "degraded": False,
        "degraded_reason": None,
        "items": [],
    }


def _expect_envelope(item: dict[str, Any]) -> dict[str, Any]:
    exp = item.get("expect")
    if isinstance(exp, dict):
        return exp
    return {}


def sanitize_contract_for_mvp(
    contract: dict[str, Any],
    *,
    issue_text: str = "",
) -> dict[str, Any]:
    """Best-effort machine fixes so fill/repair drafts can pass BC MVP."""
    data = deepcopy(contract)
    data.setdefault("items", [])
    for item in data["items"]:
        exp = item.get("expect")
        if not isinstance(exp, dict):
            exp = {}
            item["expect"] = exp
        kind = str(item.get("oracle_kind") or exp.get("oracle_kind") or "")
        # Map unknown LLM kinds onto MVP set
        kind_aliases = {
            "file_exists": "raises",
            "exists": "raises",
            "existence": "raises",
            "equal": "equality",
            "eq": "equality",
            "status": "http_status",
            "http": "http_status",
            "regex": "stdout_regex",
            "exception": "raises",
            "error": "raises",
        }
        if kind in kind_aliases:
            kind = kind_aliases[kind]
        if kind not in {
            "equality",
            "field_path",
            "contains",
            "raises",
            "http_status",
            "stdout_regex",
            "attr_error",
        }:
            kind = "raises"
        item["oracle_kind"] = kind
        exp["oracle_kind"] = kind
        if not kind:
            kind = "raises"
            item["oracle_kind"] = kind
            exp["oracle_kind"] = kind
        exp.setdefault("oracle_kind", kind)
        if kind == "field_path" and not exp.get("field_path"):
            exp["field_path"] = "value"
        if kind in ("raises", "attr_error"):
            exp.setdefault(
                "exception",
                "AttributeError" if kind == "attr_error" else "AssertionError",
            )
            item.setdefault("fail_mode", "not_implemented")
            item.setdefault("expect_confidence", "low")
        layer = str(item.get("layer") or "lib")
        if layer in ("cli", "web") and not item.get("entrypoint"):
            # Prefer degraded lib over BC-07 blocking when fill omitted entrypoint
            item["layer"] = "lib"
            item["entrypoint"] = None
        cg = item.get("call_graph")
        if not cg:
            item["call_graph"] = ["feature_api"]
        if not item.get("issue_quote") and issue_text:
            item["issue_quote"] = issue_text[: min(120, len(issue_text))]
        item.setdefault("expect_confidence", "high")
        item.setdefault("tier", "S1")
        item.setdefault("inputs", {})
        item.setdefault("fail_mode", "assert")
    if data["items"] and all(
        str(i.get("expect_confidence")) == "low" for i in data["items"]
    ):
        data["degraded"] = True
    return data


def validate_contract(
    contract: dict[str, Any],
    *,
    issue_text: str = "",
    recipe_cards: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Return {passed, blocking:[{rule_id,must_id,msg}], warnings:[...]}."""
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    items = contract.get("items") or []
    if not items:
        blocking.append(
            {"rule_id": "BC-01", "must_id": "", "msg": "items empty"}
        )
        return {"passed": False, "blocking": blocking, "warnings": warnings}

    seen_ids: set[str] = set()
    has_high = False
    has_degraded_raises = False
    require_ep = bool(
        getattr(config, "spec_parser_s1_require_entrypoint_for_cli_web", True)
    )

    for item in items:
        mid = str(item.get("must_id") or "")
        if mid in seen_ids:
            blocking.append(
                {"rule_id": "BC-12", "must_id": mid, "msg": "duplicate must_id"}
            )
        seen_ids.add(mid)

        quote = str(item.get("issue_quote") or "")
        if not quote or (issue_text and not normalize_quote_match(quote, issue_text)):
            blocking.append(
                {
                    "rule_id": "BC-02",
                    "must_id": mid,
                    "msg": "missing issue_quote or not Issue substring",
                }
            )

        kind = str(item.get("oracle_kind") or _expect_envelope(item).get("oracle_kind") or "")
        exp = _expect_envelope(item)
        if kind not in ORACLE_KINDS:
            blocking.append(
                {"rule_id": "BC-03", "must_id": mid, "msg": f"illegal oracle_kind={kind}"}
            )
        else:
            if kind in ("equality", "contains") and "value" not in exp:
                blocking.append(
                    {"rule_id": "BC-03", "must_id": mid, "msg": "expect.value required"}
                )
            if kind == "field_path" and not exp.get("field_path"):
                blocking.append(
                    {
                        "rule_id": "BC-03",
                        "must_id": mid,
                        "msg": "expect.field_path required",
                    }
                )
            if kind in ("raises", "attr_error") and not (
                exp.get("exception") or item.get("fail_mode")
            ):
                blocking.append(
                    {
                        "rule_id": "BC-03",
                        "must_id": mid,
                        "msg": "raises needs exception/fail_mode",
                    }
                )
            if kind == "http_status" and exp.get("status") is None and exp.get("value") is None:
                blocking.append(
                    {"rule_id": "BC-03", "must_id": mid, "msg": "http_status needs status"}
                )

        # BC-04 weak/empty expect
        val = exp.get("value", object())
        if not exp or (
            kind not in ("raises", "attr_error", "field_path")
            and val is object()
        ):
            if kind not in ("raises", "attr_error"):
                blocking.append(
                    {"rule_id": "BC-04", "must_id": mid, "msg": "empty expect"}
                )
        if isinstance(val, str) and val.strip().lower() in _WEAK_VALUES:
            blocking.append(
                {"rule_id": "BC-04", "must_id": mid, "msg": f"weak expect.value={val}"}
            )
        if val is None and kind in ("equality", "contains"):
            blocking.append(
                {
                    "rule_id": "BC-04",
                    "must_id": mid,
                    "msg": "null value not allowed for equality/contains",
                }
            )

        cg = item.get("call_graph") or []
        if not isinstance(cg, list) or not cg:
            blocking.append(
                {"rule_id": "BC-05", "must_id": mid, "msg": "empty call_graph"}
            )
        else:
            lowered = [str(x).split(".")[-1].lower() for x in cg]
            if all(x in _PROBE_ONLY or x.startswith("hasattr") for x in lowered):
                blocking.append(
                    {
                        "rule_id": "BC-05",
                        "must_id": mid,
                        "msg": "call_graph is existence-only probes",
                    }
                )
            for sym in cg:
                s = str(sym)
                if "._" in s or s.startswith("_"):
                    if issue_text and s.lstrip("_").split(".")[0].lower() not in issue_text.lower():
                        # private path not named in Issue
                        if "._" in s:
                            blocking.append(
                                {
                                    "rule_id": "BC-06",
                                    "must_id": mid,
                                    "msg": f"private call_graph path {s}",
                                }
                            )

        layer = str(item.get("layer") or "lib")
        if layer not in LAYERS:
            warnings.append(
                {"rule_id": "BC-W0", "must_id": mid, "msg": f"unknown layer {layer}"}
            )
        if layer in ("cli", "web") and require_ep and not item.get("entrypoint"):
            blocking.append(
                {
                    "rule_id": "BC-07",
                    "must_id": mid,
                    "msg": "web/cli S1 requires entrypoint",
                }
            )

        recipe_id = item.get("recipe_id")
        cards = recipe_cards or {}
        if recipe_id and recipe_id in cards:
            card = cards[recipe_id]
            forb = card.get("forbidden_patterns") or []
            joined = " ".join(str(x) for x in cg)
            for pat in forb:
                if pat and pat in joined:
                    blocking.append(
                        {
                            "rule_id": "BC-08",
                            "must_id": mid,
                            "msg": f"call_graph hits forbidden {pat}",
                        }
                    )
        # recipe hit without id: soft — if card patterns appear without id
        if not recipe_id and cards:
            joined = " ".join(str(x) for x in cg)
            for cid, card in cards.items():
                req = card.get("required_patterns") or []
                if req and all(p in joined for p in req[:1]):
                    # has recipe-ish symbols but no id
                    if any(p in joined for p in (card.get("forbidden_patterns") or [])):
                        blocking.append(
                            {
                                "rule_id": "BC-08",
                                "must_id": mid,
                                "msg": f"recipe-like graph without recipe_id ({cid})",
                            }
                        )

        # BC-09 / BC-09b direction conflict
        qn = _norm_ws(quote)
        if qn:
            has_req = any(k in qn for k in ("required", "must "))
            has_none = any(k in qn for k in ("none", "null"))
            if has_req and has_none and kind in ("equality", "field_path"):
                if isinstance(val, (dict, list)) and val:
                    blocking.append(
                        {
                            "rule_id": "BC-09b",
                            "must_id": mid,
                            "msg": "required+none quote vs non-null container expect",
                        }
                    )
            if "none" in qn or "null" in qn:
                if val is True or (isinstance(val, str) and val.lower() in ("true", "object")):
                    blocking.append(
                        {
                            "rule_id": "BC-09",
                            "must_id": mid,
                            "msg": "quote suggests None but expect is truthy object",
                        }
                    )
            if "false" in qn and val is True:
                blocking.append(
                    {
                        "rule_id": "BC-09",
                        "must_id": mid,
                        "msg": "quote false vs expect true",
                    }
                )

        if layer == "async" and not item.get("needs_async_harness"):
            warnings.append(
                {
                    "rule_id": "BC-10",
                    "must_id": mid,
                    "msg": "async layer should set needs_async_harness",
                }
            )

        conf = str(item.get("expect_confidence") or "high")
        if conf == "high":
            has_high = True
        if conf == "low" and kind in ("raises", "attr_error"):
            has_degraded_raises = True

        if str(exp.get("exception") or "") == "Exception":
            warnings.append(
                {"rule_id": "BC-W1", "must_id": mid, "msg": "over-broad Exception"}
            )

    if not has_high and not has_degraded_raises:
        blocking.append(
            {
                "rule_id": "BC-11",
                "must_id": "",
                "msg": "no high-confidence row and no low+raises degraded row",
            }
        )

    if len(items) == 1 and issue_text:
        # rough must count
        must_hits = len(re.findall(r"\bmust\b", issue_text, flags=re.I))
        if must_hits >= 3:
            warnings.append(
                {
                    "rule_id": "BC-W2",
                    "must_id": "",
                    "msg": "only 1 S1 row while Issue has many musts",
                }
            )

    return {
        "passed": not blocking,
        "blocking": blocking,
        "warnings": warnings,
    }


def parse_contract_json(raw: str | dict) -> dict[str, Any]:
    if isinstance(raw, dict):
        data = deepcopy(raw)
    else:
        import json

        data = json.loads(raw)
    if "items" not in data and isinstance(data.get("contract"), dict):
        data = data["contract"]
    if "items" not in data and isinstance(data, list):
        data = {"items": data, "schema_version": "bc-1", "script_tier": "S1"}
    data.setdefault("schema_version", "bc-1")
    data.setdefault("script_tier", "S1")
    data.setdefault("items", [])
    return data
