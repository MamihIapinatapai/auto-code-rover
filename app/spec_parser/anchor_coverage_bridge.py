"""Soft bridge between ScriptAnchor and coverage / over-spec hints (v3.3.1)."""

from __future__ import annotations

import re

from app.spec_parser.schema import ScriptAnchor

_CALL_ATTR_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,40})\s*\(")


def suggest_product_calls(anchor: ScriptAnchor, ac_text: str) -> list[str]:
    """Intersect AC text tokens with anchor symbol / entrypoint names."""
    blob = (ac_text or "").lower()
    out: list[str] = []
    for sym in anchor.symbols:
        if sym.name.lower() in blob or sym.name.split(".")[-1].lower() in blob:
            out.append(sym.name)
    for ep in anchor.entrypoints:
        if ep.name and ep.name.lower() in blob:
            out.append(ep.name)
    return out[:12]


def flag_over_spec_calls(script: str, anchor: ScriptAnchor, issue_text: str) -> list[str]:
    """
    Soft hints only (B5): names called in script that appear in neither Issue nor Anchor.
    Never used for hard blocking; draft score weight defaults to 0.
    """
    allowed = {s.name.split(".")[-1].lower() for s in anchor.symbols}
    allowed |= {s.name.lower() for s in anchor.symbols}
    allowed |= {ep.name.lower() for ep in anchor.entrypoints if ep.name}
    issue_l = (issue_text or "").lower()
    builtins = {
        "print",
        "len",
        "range",
        "list",
        "dict",
        "set",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "open",
        "isinstance",
        "hasattr",
        "getattr",
        "setattr",
        "Exception",
        "AssertionError",
        "AttributeError",
        "ImportError",
        "ValueError",
        "TypeError",
        "KeyError",
        "RuntimeError",
        "NotImplementedError",
        "enumerate",
        "zip",
        "map",
        "filter",
        "sorted",
        "min",
        "max",
        "sum",
        "any",
        "all",
        "super",
        "property",
        "staticmethod",
        "classmethod",
    }
    flagged: list[str] = []
    for m in _CALL_ATTR_RE.finditer(script or ""):
        name = m.group(1)
        low = name.lower()
        if low in builtins or name.startswith("_"):
            continue
        if low in allowed or name in issue_text or low in issue_l:
            continue
        if name[0].isupper() and low not in allowed:
            flagged.append(name)
    # unique preserve order
    seen: set[str] = set()
    out: list[str] = []
    for n in flagged:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:15]
