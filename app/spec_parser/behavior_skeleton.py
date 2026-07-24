"""S1 script renderer from BehaviorContract (v3.4)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.spec_parser.behavior_contract import sanitize_must_id


def _lit(value: Any) -> str:
    return repr(value)


def _primary_call(call_graph: list) -> str:
    if not call_graph:
        return "target_api"
    # Prefer last non-constructor-ish as primary, else join
    parts = [str(x) for x in call_graph]
    return parts[-1] if len(parts) == 1 else ".".join(parts[:2]) if len(parts) > 1 else parts[0]


def _arrange_from_recipe(item: dict, recipe_cards: dict | None) -> list[str]:
    lines: list[str] = []
    rid = item.get("recipe_id")
    if rid and recipe_cards and rid in recipe_cards:
        tmpl = recipe_cards[rid].get("call_graph_template") or []
        hint = recipe_cards[rid].get("hint") or ""
        if hint:
            lines.append(f"    # recipe: {hint}")
        if tmpl:
            lines.append(f"    # call_graph_template: {', '.join(str(x) for x in tmpl)}")
    inputs = item.get("inputs") or {}
    if inputs:
        lines.append(f"    inputs = {json.dumps(inputs)}")
    return lines


def _assert_block(item: dict) -> list[str]:
    kind = str(item.get("oracle_kind") or (item.get("expect") or {}).get("oracle_kind") or "equality")
    exp = item.get("expect") or {}
    lines: list[str] = []
    if kind == "raises" or kind == "attr_error":
        exc = exp.get("exception") or (
            "AttributeError" if kind == "attr_error" else "Exception"
        )
        lines.append(f"    with pytest.raises({exc}):")
        lines.append("        raise AssertionError('NOT_IMPLEMENTED')")
        return lines
    if kind == "http_status":
        status = exp.get("status", exp.get("value", 200))
        lines.append(f"    assert resp.status == {int(status)}")
        lines.append("    # NOT_IMPLEMENTED marker for FEATURE calib on buggy code")
        lines.append("    raise AssertionError('NOT_IMPLEMENTED')")
        return lines
    if kind == "stdout_regex":
        pat = exp.get("pattern") or exp.get("value") or ".*"
        lines.append(f"    assert re.search({_lit(pat)}, stdout or '')")
        lines.append("    raise AssertionError('NOT_IMPLEMENTED')")
        return lines
    if kind == "field_path":
        fp = exp.get("field_path") or "value"
        val = exp.get("value")
        lines.append(f"    assert result.{fp} == {_lit(val)}")
        lines.append("    raise AssertionError('NOT_IMPLEMENTED')")
        return lines
    if kind == "contains":
        val = exp.get("value")
        lines.append(f"    assert {_lit(val)} in result")
        lines.append("    raise AssertionError('NOT_IMPLEMENTED')")
        return lines
    # equality default
    val = exp.get("value")
    lines.append(f"    assert result == {_lit(val)}")
    lines.append("    raise AssertionError('NOT_IMPLEMENTED')")
    return lines


def render_item_function(item: dict, recipe_cards: dict | None = None) -> str:
    mid = sanitize_must_id(str(item.get("must_id") or "M1"))
    layer = str(item.get("layer") or "lib")
    cg = item.get("call_graph") or ["target"]
    primary = _primary_call(cg)
    entry = item.get("entrypoint") or "/"
    lines = [f"# --- AC-{mid} ---", f"def test_ac_{mid}():"]
    lines.extend(_arrange_from_recipe(item, recipe_cards) or ["    # arrange"])

    body: list[str] = []
    if layer == "web":
        body.append("    from aiohttp.test_utils import TestClient  # type: ignore")
        body.append(f"    path = {_lit(entry)}")
        body.append(f"    # call_graph: {', '.join(str(x) for x in cg)}")
        body.append("    resp = type('R', (), {'status': 501, 'path': path})()")
        body.append(f"    _ = {_lit(primary)}")
    elif layer == "cli":
        body.append("    import subprocess")
        body.append(f"    entrypoint = {_lit(entry)}")
        body.append(f"    # call_graph: {', '.join(str(x) for x in cg)}")
        body.append("    stdout = ''")
        body.append(f"    result = entrypoint")
        body.append(f"    _ = {_lit(primary)}")
    elif layer == "async":
        body.append("    async def _body():")
        body.append(f"        # call_graph: {', '.join(str(x) for x in cg)}")
        body.append(f"        result = await None  # placeholder for {primary}")
        for ln in _assert_block(item):
            # indent extra for _body
            body.append("    " + ln)
        body.append("        raise AssertionError('NOT_IMPLEMENTED')")
        body.append("    asyncio.run(_body())")
        return "\n".join(lines + body) + "\n"
    else:
        # lib
        body.append(f"    # call_graph: {', '.join(str(x) for x in cg)}")
        for sym in cg:
            body.append(f"    _sym_{re.sub(r'[^A-Za-z0-9_]', '_', str(sym))} = {_lit(sym)}")
        body.append(f"    result = {_lit(None)}  # invoke {primary} with inputs")

    if layer != "async":
        body.extend(_assert_block(item))
    return "\n".join(lines + body) + "\n"


def render_s1_script(
    contract: dict[str, Any],
    *,
    recipe_cards: dict | None = None,
) -> str:
    header = [
        '"""Auto-generated S1 acceptance script from BehaviorContract (v3.4)."""',
        "from __future__ import annotations",
        "",
        "import asyncio",
        "import re",
        "",
        "import pytest",
        "",
    ]
    parts = ["\n".join(header)]
    for item in contract.get("items") or []:
        parts.append(render_item_function(item, recipe_cards=recipe_cards))
    if len(parts) == 1:
        parts.append(
            "# --- AC-M1 ---\n"
            "def test_ac_M1():\n"
            "    raise AssertionError('NOT_IMPLEMENTED')\n"
        )
    return "\n".join(parts)
