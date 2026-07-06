"""Language-level entity resolution policies (repo-agnostic)."""

from __future__ import annotations

AMBIGUOUS_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "__init__",
        "__new__",
        "__str__",
        "__repr__",
        "__eq__",
        "__hash__",
        "main",
        "run",
        "setup",
        "test",
        "execute",
    }
)

ISSUE_CLASS_STOPLIST: frozenset[str] = frozenset(
    {
        "i",
        "if",
        "the",
        "this",
        "that",
        "when",
        "calling",
        "call",
        "value",
        "error",
        "true",
        "false",
        "none",
        "not",
        "and",
        "or",
        "for",
        "with",
        "from",
        "into",
        "using",
        "should",
        "would",
        "could",
        "instead",
        "raises",
        "raised",
    }
)

SCOPE_NOISE_SUFFIXES: tuple[str, ...] = (
    " constructor logic for handling cycles",
    " constructor logic",
    " logic for handling",
    " for handling cycles",
)


def normalize_fix_scope_label(label: str) -> str:
    text = label.strip()
    lower = text.lower()
    for suffix in SCOPE_NOISE_SUFFIXES:
        if lower.endswith(suffix):
            return text[: -len(suffix)].strip()
    if lower.endswith(" constructor"):
        return text[: -len(" constructor")].strip()
    return text


def is_ambiguous_method(name: str) -> bool:
    short = name.split(".")[-1]
    return short in AMBIGUOUS_METHOD_NAMES


def bound_method_name(class_name: str, method: str) -> str:
    return f"{class_name}.{method}"
