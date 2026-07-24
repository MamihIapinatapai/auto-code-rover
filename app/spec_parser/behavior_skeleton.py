"""S1 Real Renderer (scheme A): CallPlan Bind + string Emit (Spec Parser v3.5 / WP-α)."""

from __future__ import annotations

import ast
import builtins
import re
from dataclasses import dataclass, field
from typing import Any

from app import config
from app.spec_parser.behavior_contract import sanitize_must_id
from app.spec_parser.failure_semantics import check_failure_semantics
from app.spec_parser.recipe_loader import load_recipe_cards, recipe_compliance

_SLOT_RE = re.compile(r"__SLOT_([A-Za-z_][A-Za-z0-9_]*)__")
_BRACE_SLOT_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class RenderResult:
    ok: bool
    script: str | None = None
    reason_code: str | None = None
    per_must: dict[str, str] | None = None


@dataclass
class CallPlan:
    must_id: str
    imports: list[str] = field(default_factory=list)
    arrange_lines: list[str] = field(default_factory=list)
    call_expr: str = ""
    bind_mode: str = "recipe"  # recipe | snippet | signature
    layer: str = "lib"
    needs_await: bool = False
    result_name: str = "result"
    recipe_id: str | None = None
    source_snippet_id: str | None = None
    bound_names: set[str] = field(default_factory=set)
    oracle_kind: str = "equality"
    expect: dict[str, Any] = field(default_factory=dict)


def _lit(value: Any) -> str:
    return repr(value)


def _normalize_slots_text(text: str) -> str:
    """Normalize {key} style slots (when listed) to __SLOT_key__ — callers decide."""
    return text


_IDENT_SLOT_KEYS = frozenset({"model", "tp", "cls", "type", "name", "exc", "exception", "handler", "field_name"})


def _slot_value_expr(key: str, value: Any) -> str:
    """Render slot value: bare identifier for type/name slots when safe, else repr."""
    if (
        key in _IDENT_SLOT_KEYS
        and isinstance(value, str)
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value)
    ):
        return value
    return _lit(value)


def _fill_slots(text: str, inputs: dict[str, Any], aliases: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Replace __SLOT_k__ with inputs[k] expression. Returns (text, missing_keys)."""
    aliases = aliases or {}
    # Build canonical inputs via aliases (payload -> data)
    canon: dict[str, Any] = dict(inputs)
    for alias, target in aliases.items():
        if alias in canon and target not in canon:
            canon[target] = canon[alias]
    missing: list[str] = []

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in canon:
            missing.append(key)
            return m.group(0)
        return _slot_value_expr(key, canon[key])

    out = _SLOT_RE.sub(repl, text)
    return out, missing


def _snippet_list(usage_snippets: dict | list | None) -> list[dict]:
    if usage_snippets is None:
        return []
    if isinstance(usage_snippets, dict):
        return list(usage_snippets.get("snippets") or [])
    return list(usage_snippets)


def _resolve_inputs(item: dict) -> dict[str, Any]:
    return dict(item.get("inputs") or {})


def _bind_recipe(
    item: dict, card: dict
) -> tuple[CallPlan | None, str | None]:
    et = card.get("emit_template")
    if not isinstance(et, dict):
        return None, None
    mid = sanitize_must_id(str(item.get("must_id") or "M1"))
    aliases = dict(et.get("slot_aliases") or {})
    slots_needed = list(et.get("slots_from_inputs") or [])
    inputs = _resolve_inputs(item)
    # alias normalize into inputs
    for alias, target in aliases.items():
        if alias in inputs and target not in inputs:
            inputs[target] = inputs[alias]

    missing = [k for k in slots_needed if k not in inputs]
    if missing:
        return None, "MISSING_SLOT"

    imports = [str(x) for x in (et.get("imports") or [])]
    arrange_raw = list(et.get("arrange") or [])
    call_raw = str(et.get("call_expr") or "")
    # Also accept {key} braces for keys in slots_from_inputs → normalize
    for key in slots_needed:
        brace = "{" + key + "}"
        slot = f"__SLOT_{key}__"
        call_raw = call_raw.replace(brace, slot)
        arrange_raw = [a.replace(brace, slot) for a in arrange_raw]

    call_expr, miss2 = _fill_slots(call_raw, inputs, aliases)
    arrange_lines: list[str] = []
    for a in arrange_raw:
        filled, m = _fill_slots(a, inputs, aliases)
        miss2.extend(m)
        for line in filled.splitlines() or [filled]:
            arrange_lines.append(line)
    # arrange_prelude from inputs
    prelude = inputs.get("arrange_prelude")
    if isinstance(prelude, str) and prelude.strip():
        arrange_lines.extend(prelude.splitlines())

    if miss2:
        return None, "MISSING_SLOT"

    # Recipe required/forbidden on expanded fragment
    fragment = "\n".join(imports + arrange_lines + [call_expr])
    for pat in card.get("forbidden_patterns") or []:
        needle = str(pat).replace("...", "")
        if needle and needle in fragment:
            return None, "RECIPE_UNSAT"
    for pat in card.get("required_patterns") or []:
        if pat and pat not in fragment:
            return None, "RECIPE_UNSAT"

    bound = _names_from_imports(imports) | _names_bound_in_arrange(arrange_lines)
    plan = CallPlan(
        must_id=mid,
        imports=imports,
        arrange_lines=arrange_lines,
        call_expr=call_expr,
        bind_mode="recipe",
        layer=str(item.get("layer") or card.get("layer") or "lib"),
        needs_await=bool(et.get("needs_await") or item.get("needs_async_harness")),
        result_name=str(et.get("result_name") or ("resp" if (item.get("layer") or "") == "web" else "result")),
        recipe_id=str(card.get("id") or item.get("recipe_id") or ""),
        bound_names=bound,
        oracle_kind=str(item.get("oracle_kind") or (item.get("expect") or {}).get("oracle_kind") or "equality"),
        expect=dict(item.get("expect") or {}),
    )
    unbound = _unbound_names(plan)
    if unbound:
        return None, "UNBOUND_NAME"
    return plan, None


def _names_from_imports(imports: list[str]) -> set[str]:
    names: set[str] = set()
    for line in imports:
        try:
            mod = ast.parse(line)
        except SyntaxError:
            # from x import a, b
            m = re.search(r"import\s+(.+)$", line)
            if m:
                for part in m.group(1).split(","):
                    part = part.strip().split(" as ")[-1].strip()
                    if part:
                        names.add(part.split(".")[0])
            continue
        for node in ast.walk(mod):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    names.add(alias.asname or alias.name)
    return names


def _names_bound_in_arrange(lines: list[str]) -> set[str]:
    names: set[str] = set()
    src = "\n".join(lines)
    if not src.strip():
        return names
    try:
        tree = ast.parse(src)
    except SyntaxError:
        # class Name( — fallback regex
        for m in re.finditer(r"^\s*class\s+(\w+)", src, re.MULTILINE):
            names.add(m.group(1))
        for m in re.finditer(r"^\s*(\w+)\s*=", src, re.MULTILINE):
            names.add(m.group(1))
        return names
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.FunctionDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _unbound_names(plan: CallPlan) -> set[str]:
    builtin_names = set(dir(builtins))
    known = set(plan.bound_names) | builtin_names | {
        "pytest",
        "asyncio",
        "re",
        plan.result_name,
    }
    # imports already in bound_names
    chunk = "\n".join(plan.arrange_lines + [f"_ = {plan.call_expr}"])
    try:
        tree = ast.parse(chunk)
    except SyntaxError:
        return set()
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    # Names assigned in arrange are bound
    assigned = _names_bound_in_arrange(plan.arrange_lines)
    known |= assigned
    return {n for n in used if n not in known and not n.startswith("_")}


def _bind_snippet(
    item: dict,
    snippets: list[dict],
    *,
    recipe_cards: dict | None,
) -> tuple[CallPlan | None, str | None]:
    mid = sanitize_must_id(str(item.get("must_id") or "M1"))
    inputs = _resolve_inputs(item)
    rid = item.get("recipe_id")
    cg = [str(x) for x in (item.get("call_graph") or [])]

    candidates = [
        s
        for s in snippets
        if s.get("printable")
        and s.get("bind_ready", True)
        and str(s.get("confidence") or "low") in {"high", "medium"}
    ]
    # Prefer recipe-aligned / matching api
    def score(s: dict) -> tuple:
        aligned = 1 if s.get("recipe_aligned") or (rid and s.get("recipe_id") == rid) else 0
        api = str(s.get("api_name") or "")
        hit = 1 if any(c in api for c in cg) else 0
        conf = {"high": 2, "medium": 1}.get(str(s.get("confidence")), 0)
        return (aligned, hit, conf)

    candidates.sort(key=score, reverse=True)
    if not candidates:
        return None, "NO_USAGE_FUEL"

    # Ambiguous: multiple mutually exclusive call_patterns without recipe lock
    if not rid and len(candidates) > 1:
        patterns = {s.get("call_pattern") for s in candidates[:3]}
        if len(patterns) > 1:
            # still try first if they share api; else AMBIGUOUS
            apis = {s.get("api_name") for s in candidates[:3]}
            if len(apis) > 1:
                return None, "AMBIGUOUS_API"

    last_reason = "BIND_INPUTS_FAIL"
    for snip in candidates:
        pattern = str(snip.get("call_pattern") or "")
        if not pattern:
            continue
        imports_line = str(snip.get("import_path") or "")
        imports = [imports_line] if imports_line.strip() else []
        aliases = {}
        if rid and recipe_cards and rid in recipe_cards:
            et = (recipe_cards[rid] or {}).get("emit_template") or {}
            aliases = dict(et.get("slot_aliases") or {})

        call_expr = pattern
        if "__SLOT_" in pattern:
            call_expr, missing = _fill_slots(pattern, inputs, aliases)
            if missing:
                last_reason = "MISSING_SLOT"
                continue
        else:
            # P2 narrow AST: single trailing Call only — skip if multi-stmt
            if ";" in pattern or "\n" in pattern.strip():
                last_reason = "BIND_INPUTS_FAIL"
                continue
            try:
                expr_ast = ast.parse(pattern, mode="eval")
            except SyntaxError:
                last_reason = "BIND_INPUTS_FAIL"
                continue
            if not isinstance(expr_ast.body, ast.Call):
                last_reason = "BIND_INPUTS_FAIL"
                continue
            # Only allow if we can leave as-is when no inputs, or fail
            if inputs:
                last_reason = "BIND_INPUTS_FAIL"
                continue
            call_expr = pattern

        arrange_lines: list[str] = []
        prelude = inputs.get("arrange_prelude")
        if isinstance(prelude, str) and prelude.strip():
            arrange_lines.extend(prelude.splitlines())

        # parse check
        try:
            ast.parse("\n".join(arrange_lines + [f"result = {call_expr}"]))
        except SyntaxError:
            last_reason = "BIND_INPUTS_FAIL"
            continue

        bound = _names_from_imports(imports) | _names_bound_in_arrange(arrange_lines)
        plan = CallPlan(
            must_id=mid,
            imports=imports,
            arrange_lines=arrange_lines,
            call_expr=call_expr,
            bind_mode="snippet",
            layer=str(item.get("layer") or snip.get("layer_hint") or "lib"),
            needs_await=bool(item.get("needs_async_harness")),
            result_name="resp" if str(item.get("layer")) == "web" else "result",
            recipe_id=str(rid) if rid else None,
            source_snippet_id=str(snip.get("snippet_id") or ""),
            bound_names=bound,
            oracle_kind=str(
                item.get("oracle_kind")
                or (item.get("expect") or {}).get("oracle_kind")
                or "equality"
            ),
            expect=dict(item.get("expect") or {}),
        )
        if _unbound_names(plan):
            last_reason = "UNBOUND_NAME"
            continue
        return plan, None
    return None, last_reason


def _bind_item(
    item: dict,
    *,
    recipe_cards: dict | None,
    usage_snippets: list[dict],
) -> tuple[CallPlan | None, str]:
    cards = recipe_cards or {}
    rid = item.get("recipe_id")
    layer = str(item.get("layer") or "lib")
    if layer not in {"lib", "async", "web", "cli"}:
        return None, "LAYER_UNSUPPORTED"

    # Tier 1: recipe emit_template
    if rid and rid in cards and cards[rid].get("emit_template"):
        plan, err = _bind_recipe(item, cards[rid])
        if plan is not None:
            return plan, "ok"
        if err:
            return None, err

    # Tier 2: printable snippets
    plan, err = _bind_snippet(item, usage_snippets, recipe_cards=cards)
    if plan is not None:
        return plan, "ok"

    # Tier 3 signature — default off
    if getattr(config, "spec_parser_enable_bind_mode_signature", False):
        return None, "NO_USAGE_FUEL"

    return None, err or "NO_USAGE_FUEL"


def _oracle_lines(plan: CallPlan) -> list[str]:
    kind = plan.oracle_kind
    exp = plan.expect or {}
    rn = plan.result_name
    if kind in {"raises", "attr_error"}:
        return []  # handled in act
    if kind == "http_status":
        status = exp.get("status", exp.get("value", 200))
        return [f"assert {rn}.status == {int(status)}"]
    if kind == "stdout_regex":
        pat = exp.get("pattern") or exp.get("value") or ".*"
        return [f"assert re.search({_lit(pat)}, stdout or '')"]
    if kind == "field_path":
        fp = exp.get("field_path") or "value"
        return [f"assert {rn}.{fp} == {_lit(exp.get('value'))}"]
    if kind == "contains":
        return [f"assert {_lit(exp.get('value'))} in {rn}"]
    return [f"assert {rn} == {_lit(exp.get('value'))}"]


def _emit_act(plan: CallPlan) -> list[str]:
    kind = plan.oracle_kind
    exp = plan.expect or {}
    call = plan.call_expr
    rn = plan.result_name
    if kind in {"raises", "attr_error"}:
        exc = exp.get("exception") or (
            "AttributeError" if kind == "attr_error" else "Exception"
        )
        return [f"with pytest.raises({exc}):", f"    {call}"]
    if plan.needs_await or plan.layer == "async":
        return [f"{rn} = await {call}"]
    return [f"{rn} = {call}"]


def _emit_function(plan: CallPlan) -> str:
    mid = plan.must_id
    lines = [f"# --- AC-{mid} ---", f"def test_ac_{mid}():"]
    body: list[str] = []

    for al in plan.arrange_lines:
        # arrange may be multi-line class; indent each line
        for i, ln in enumerate(al.splitlines() or [al]):
            body.append(f"    {ln}" if ln.strip() else "")

    if plan.layer == "async" or plan.needs_await:
        body.append("    async def _body():")
        for ln in _emit_act(plan):
            body.append(f"        {ln}")
        for ln in _oracle_lines(plan):
            body.append(f"        {ln}")
        body.append("    asyncio.run(_body())")
    else:
        for ln in _emit_act(plan):
            body.append(f"    {ln}")
        for ln in _oracle_lines(plan):
            body.append(f"    {ln}")

    return "\n".join(lines + body) + "\n"


def _emit_script(plans: list[CallPlan]) -> str:
    imports: list[str] = []
    seen: set[str] = set()
    needs_asyncio = any(p.layer == "async" or p.needs_await for p in plans)
    needs_re = any(p.oracle_kind == "stdout_regex" for p in plans)
    for p in plans:
        for imp in p.imports:
            if imp and imp not in seen:
                seen.add(imp)
                imports.append(imp)
    header = [
        '"""Auto-generated S1 acceptance script from BehaviorContract (v3.5 S1 / scheme A)."""',
        "from __future__ import annotations",
        "",
    ]
    if needs_asyncio:
        header.append("import asyncio")
    if needs_re:
        header.append("import re")
    if needs_asyncio or needs_re:
        header.append("")
    header.append("import pytest")
    header.append("")
    for imp in sorted(imports):
        header.append(imp)
    if imports:
        header.append("")

    parts = ["\n".join(header)]
    for p in plans:
        parts.append(_emit_function(p))
    return "\n".join(parts)


def render_s1_script(
    contract: dict[str, Any],
    *,
    recipe_cards: dict | None = None,
    usage_snippets: dict | list | None = None,
    anchor: Any | None = None,
) -> RenderResult:
    """Bind + Emit scheme A. On failure: ok=False and script=None (no stub chars)."""
    del anchor  # reserved for tier-3 / future
    cards = recipe_cards if recipe_cards is not None else load_recipe_cards()
    snippets = _snippet_list(usage_snippets)
    items = list(contract.get("items") or [])
    per_must: dict[str, str] = {}

    if not items:
        return RenderResult(ok=False, script=None, reason_code="NO_USAGE_FUEL", per_must={})

    plans: list[CallPlan] = []
    for item in items:
        mid = sanitize_must_id(str(item.get("must_id") or "M1"))
        plan, status = _bind_item(item, recipe_cards=cards, usage_snippets=snippets)
        if plan is None:
            per_must[mid] = status
            # All-or-nothing
            return RenderResult(
                ok=False,
                script=None,
                reason_code=status,
                per_must=per_must,
            )
        per_must[mid] = "ok"
        plans.append(plan)

    script = _emit_script(plans)

    # Syntax check
    try:
        ast.parse(script)
    except SyntaxError:
        return RenderResult(
            ok=False, script=None, reason_code="SELF_CHECK_FAIL", per_must=per_must
        )

    # Failure semantics self-check (DRY with linter)
    if getattr(config, "spec_parser_enable_failure_semantics_check", True):
        recipe_ids = [p.recipe_id for p in plans if p.recipe_id]
        rid = recipe_ids[0] if recipe_ids else None
        fs = check_failure_semantics(script, recipe_id=rid, recipe_cards=cards)
        if fs.blocking:
            return RenderResult(
                ok=False,
                script=None,
                reason_code="SELF_CHECK_FAIL",
                per_must=per_must,
            )

    # Recipe compliance for blocking cards
    for p in plans:
        if p.recipe_id and not recipe_compliance(script, p.recipe_id):
            card = cards.get(p.recipe_id) or {}
            if card.get("blocking", True):
                return RenderResult(
                    ok=False,
                    script=None,
                    reason_code="RECIPE_UNSAT",
                    per_must=per_must,
                )

    return RenderResult(ok=True, script=script, reason_code=None, per_must=per_must)
