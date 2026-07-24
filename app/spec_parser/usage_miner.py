"""UsageMiner: mine printable Call-shape snippets from the repo (Spec Parser v3.5 / WP-γ MVP)."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from app.spec_parser.recipe_loader import load_recipe_cards, match_recipe_hints

_IDENT_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_SLOT_RE = re.compile(r"__SLOT_([A-Za-z_][A-Za-z0-9_]*)__")


def mine_usage(
    repo_path: str | Path,
    issue_text: str,
    anchor: Any | None = None,
    recipe_cards: dict | None = None,
    budget_files: int = 80,
) -> dict[str, Any]:
    """Mine usage snippets. MVP: L0 funnel + limited Call-shape scan + Recipe seeds."""
    root = Path(repo_path) if repo_path else Path(".")
    cards = recipe_cards if recipe_cards is not None else load_recipe_cards()
    matched = match_recipe_hints(issue_text, _anchor_summary(anchor))

    recipe_forced: list[str] = []
    for card in matched:
        for tok in card.get("call_graph_template") or []:
            t = str(tok)
            if t not in recipe_forced:
                recipe_forced.append(t)

    issue_named = _issue_entities(issue_text)
    anchor_hit = _anchor_symbols(anchor)

    # L0 = union; recipe forced always included
    l0: list[str] = []
    for name in recipe_forced + issue_named + anchor_hit:
        if name and name not in l0:
            l0.append(name)

    candidate_funnel = {
        "recipe_forced": recipe_forced,
        "issue_named": issue_named,
        "anchor_hit": anchor_hit,
    }

    snippets: list[dict[str, Any]] = []

    # Recipe seeds (may be enough for printable via emit_template downstream)
    for card in matched:
        tmpl = card.get("call_graph_template") or []
        et = card.get("emit_template") or {}
        call_expr = str(et.get("call_expr") or "")
        imports = list(et.get("imports") or [])
        slot_keys = list(et.get("slots_from_inputs") or [])
        if call_expr:
            snippets.append(
                {
                    "snippet_id": f"recipe-{card.get('id')}",
                    "api_name": ".".join(str(x) for x in tmpl) or str(card.get("id")),
                    "import_path": imports[0] if imports else "",
                    "signature": "",
                    "call_pattern": call_expr,
                    "slot_keys": slot_keys or _SLOT_RE.findall(call_expr),
                    "layer_hint": card.get("layer") or "lib",
                    "source_kind": "recipe_seed",
                    "source_path": "",
                    "source_lineno": 0,
                    "confidence": "high",
                    "printable": True,
                    "bind_ready": True,
                    "forbidden_nearby": list(card.get("forbidden_patterns") or []),
                    "recipe_id": card.get("id"),
                    "recipe_aligned": True,
                }
            )

    if not l0 and not snippets:
        return {
            "task_id": "",
            "candidate_funnel": candidate_funnel,
            "sufficiency": "insufficient",
            "sufficiency_reason": "no_l0",
            "snippets": [],
            "summary_for_prompt": "(no usage fuel)",
        }

    # Scan limited files for Call-shape when L0 non-empty
    if l0 and root.is_dir():
        scanned = 0
        for path in _candidate_files(root, budget_files):
            if scanned >= budget_files:
                break
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if not any(n in text for n in l0):
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            source_kind = _source_kind(rel)
            for snip in _extract_call_shapes(tree, text, l0, rel, source_kind, matched, cards):
                snippets.append(snip)
            # Early stop if we already have printable medium+
            if _has_printable(snippets) and scanned >= 8:
                break

    # Drop forbidden
    snippets = [s for s in snippets if not _forbidden_hit(s, matched, cards)]

    # Dedup / top-k per api
    snippets = _rank_and_trim(snippets, topk=3)

    sufficiency, reason = _sufficiency(snippets, matched)
    return {
        "task_id": "",
        "candidate_funnel": candidate_funnel,
        "sufficiency": sufficiency,
        "sufficiency_reason": reason,
        "snippets": snippets,
        "summary_for_prompt": format_usage_for_prompt(
            {
                "snippets": snippets,
                "sufficiency": sufficiency,
                "sufficiency_reason": reason,
            }
        ),
    }


def format_usage_for_prompt(result: dict[str, Any]) -> str:
    snips = result.get("snippets") or []
    if not snips:
        return (
            f"UsageMiner: sufficiency={result.get('sufficiency')} "
            f"({result.get('sufficiency_reason')}); no snippets."
        )
    lines = [
        f"UsageMiner: sufficiency={result.get('sufficiency')} "
        f"({result.get('sufficiency_reason')}); top snippets:"
    ]
    for s in snips[:5]:
        lines.append(
            f"- [{s.get('confidence')}/{s.get('source_kind')}] "
            f"{s.get('api_name')}: `{s.get('call_pattern')}` "
            f"import=`{s.get('import_path')}` printable={s.get('printable')}"
        )
    return "\n".join(lines)


def _anchor_summary(anchor: Any) -> str:
    if anchor is None:
        return ""
    if isinstance(anchor, str):
        return anchor
    if isinstance(anchor, dict):
        return " ".join(str(x) for x in (anchor.get("symbols") or [])[:20])
    symbols = getattr(anchor, "symbols", None) or []
    names = []
    for s in symbols[:20]:
        names.append(getattr(s, "name", None) or str(s))
    return " ".join(names)


def _anchor_symbols(anchor: Any) -> list[str]:
    if anchor is None:
        return []
    if isinstance(anchor, dict):
        out = []
        for s in anchor.get("symbols") or []:
            if isinstance(s, dict) and s.get("name"):
                out.append(str(s["name"]))
            elif isinstance(s, str):
                out.append(s)
        return out
    out = []
    for s in getattr(anchor, "symbols", None) or []:
        n = getattr(s, "name", None)
        if n:
            out.append(str(n))
    return out


def _issue_entities(issue_text: str) -> list[str]:
    # Lightweight CamelCase / dotted API tokens
    found: list[str] = []
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9_]{2,}|[a-z]+(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", issue_text or ""):
        tok = m.group(1)
        if "." in tok:
            tok = tok.split(".")[-1]
        if tok.lower() in {"the", "this", "when", "with", "from", "that", "should"}:
            continue
        if tok not in found:
            found.append(tok)
    return found[:20]


def _candidate_files(root: Path, budget: int) -> list[Path]:
    out: list[Path] = []
    # Prefer examples/, then limited python
    for pat in ("examples/**/*.py", "example/**/*.py", "docs/**/*.py"):
        for p in root.glob(pat):
            if p.is_file():
                out.append(p)
            if len(out) >= budget:
                return out
    # tests call-shape (D1)
    for pat in ("tests/**/*.py", "test/**/*.py", "**/test_*.py"):
        for p in root.glob(pat):
            if p.is_file() and p not in out:
                out.append(p)
            if len(out) >= budget:
                return out
    # business modules
    for p in root.rglob("*.py"):
        if p.is_file() and p not in out:
            rel = str(p.relative_to(root)) if p.is_relative_to(root) else str(p)
            if any(x in rel for x in (".git", "venv", "site-packages", "node_modules")):
                continue
            out.append(p)
        if len(out) >= budget:
            break
    return out[:budget]


def _source_kind(rel: str) -> str:
    low = rel.lower().replace("\\", "/")
    if "example" in low:
        return "examples"
    if "/test" in f"/{low}" or low.startswith("test") or "/tests/" in f"/{low}":
        return "test_call_shape"
    if low.endswith(".md") or "readme" in low:
        return "readme"
    return "business_call"


def _extract_call_shapes(
    tree: ast.AST,
    text: str,
    l0: list[str],
    rel: str,
    source_kind: str,
    matched: list[dict],
    cards: dict,
) -> list[dict]:
    l0_set = set(l0)
    imports = _import_lines(tree)
    out: list[dict] = []
    # Drop Assert nodes conceptually by skipping them when unparsing closures
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if not name or name not in l0_set:
            # also match attr root
            root = _call_root_name(node)
            if root not in l0_set and name not in l0_set:
                continue
        if name.startswith("_"):
            continue
        if name in {"hasattr", "getattr", "setattr", "print", "len", "type"}:
            continue
        try:
            raw = ast.unparse(node)
        except Exception:  # noqa: BLE001
            continue
        pattern, slot_keys = _normalize_slots(node, raw)
        printable = "__SLOT_" in pattern
        conf = "medium"
        if source_kind == "examples":
            conf = "high"
        elif source_kind == "readme":
            conf = "medium"
        elif source_kind == "test_call_shape":
            conf = "medium"
        recipe_id = None
        aligned = False
        for card in matched:
            tmpl = [str(x) for x in (card.get("call_graph_template") or [])]
            if name in tmpl or any(t in pattern for t in tmpl):
                recipe_id = card.get("id")
                aligned = True
                conf = "high"
                break
        out.append(
            {
                "snippet_id": f"u-{rel}-{getattr(node, 'lineno', 0)}",
                "api_name": name,
                "import_path": imports[0] if imports else "",
                "signature": "",
                "call_pattern": pattern,
                "slot_keys": slot_keys,
                "layer_hint": "lib",
                "source_kind": source_kind,
                "source_path": rel,
                "source_lineno": int(getattr(node, "lineno", 0) or 0),
                "confidence": conf,
                "printable": printable,
                "bind_ready": printable,
                "forbidden_nearby": [],
                "recipe_id": recipe_id,
                "recipe_aligned": aligned,
            }
        )
        if len(out) >= 6:
            break
    return out


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _call_root_name(node: ast.Call) -> str | None:
    f = node.func
    while isinstance(f, ast.Attribute):
        f = f.value
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Call):
        return _call_name(f)
    return None


def _import_lines(tree: ast.AST) -> list[str]:
    lines: list[str] = []
    for node in getattr(tree, "body", []) or []:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            try:
                lines.append(ast.unparse(node))
            except Exception:  # noqa: BLE001
                continue
    return lines


def _normalize_slots(node: ast.Call, raw: str) -> tuple[str, list[str]]:
    """Replace simple Constant / Name args with __SLOT_*__ when keyword known."""
    slot_keys: list[str] = []
    # Keyword args
    for kw in node.keywords:
        if not kw.arg:
            continue
        if isinstance(kw.value, (ast.Constant, ast.Name, ast.Dict, ast.List)):
            key = kw.arg
            slot_keys.append(key)
            try:
                old = ast.unparse(kw.value)
            except Exception:  # noqa: BLE001
                continue
            raw = raw.replace(f"{key}={old}", f"{key}=__SLOT_{key}__", 1)
    # Positional: map common first args
    pos_names = ["data", "tp", "arg2", "arg3"]
    for i, arg in enumerate(node.args[:3]):
        if isinstance(arg, (ast.Constant, ast.Dict, ast.List, ast.Name)):
            key = pos_names[i] if i < len(pos_names) else f"arg{i}"
            # Prefer 'data' for dict constants
            if isinstance(arg, ast.Dict):
                key = "data"
            slot_keys.append(key)
            try:
                old = ast.unparse(arg)
            except Exception:  # noqa: BLE001
                continue
            raw = raw.replace(old, f"__SLOT_{key}__", 1)
    # Dedup keys preserving order
    seen: set[str] = set()
    keys: list[str] = []
    for k in slot_keys:
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return raw, keys


def _forbidden_hit(snip: dict, matched: list[dict], cards: dict) -> bool:
    pattern = str(snip.get("call_pattern") or "")
    for card in matched:
        for pat in card.get("forbidden_patterns") or []:
            needle = str(pat).replace("...", "")
            if needle and needle in pattern:
                return True
    rid = snip.get("recipe_id")
    if rid and rid in (cards or {}):
        for pat in (cards[rid].get("forbidden_patterns") or []):
            needle = str(pat).replace("...", "")
            if needle and needle in pattern:
                return True
    return False


def _has_printable(snippets: list[dict]) -> bool:
    return any(
        s.get("printable") and str(s.get("confidence")) in {"high", "medium"}
        for s in snippets
    )


def _rank_and_trim(snippets: list[dict], topk: int = 3) -> list[dict]:
    def key(s: dict) -> tuple:
        conf = {"high": 3, "medium": 2, "low": 1}.get(str(s.get("confidence")), 0)
        src = {
            "recipe_seed": 6,
            "examples": 5,
            "business_call": 4,
            "test_call_shape": 3,
            "docstring": 2,
            "readme": 1,
            "anchor_only": 0,
        }.get(str(s.get("source_kind")), 0)
        return (
            1 if s.get("recipe_aligned") else 0,
            1 if s.get("printable") else 0,
            src,
            conf,
        )

    snippets = sorted(snippets, key=key, reverse=True)
    by_api: dict[str, list[dict]] = {}
    out: list[dict] = []
    for s in snippets:
        api = str(s.get("api_name") or "")
        bucket = by_api.setdefault(api, [])
        if len(bucket) >= topk:
            continue
        bucket.append(s)
        out.append(s)
    return out


def _sufficiency(snippets: list[dict], matched: list[dict]) -> tuple[str, str]:
    if any(
        s.get("printable") and str(s.get("confidence")) in {"high", "medium"}
        for s in snippets
    ):
        return "printable", "has_medium_call_pattern"
    if any((c.get("emit_template") or {}).get("call_expr") for c in matched):
        return "printable", "recipe_expandable"
    if snippets:
        return "prompt_only", "sig_only"
    return "insufficient", "no_l0"
