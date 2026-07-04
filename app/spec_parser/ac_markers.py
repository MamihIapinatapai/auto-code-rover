"""Unified AC section marker parsing for acceptance scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

AC_ID_PATTERN = r"AC-[A-Z0-9]+"

MARKER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "dash",
        re.compile(
            rf"---\s*({AC_ID_PATTERN})(?:\s*:|\s*---|\s|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "equals",
        re.compile(rf"===\s*({AC_ID_PATTERN})\s*===", re.IGNORECASE),
    ),
    (
        "comment_colon",
        re.compile(rf"^\s*#\s*({AC_ID_PATTERN})\s*:", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "fail_marker",
        re.compile(
            rf"print\s*\(\s*['\"]?({AC_ID_PATTERN})\s+(?:PASS|FAIL)",
            re.IGNORECASE,
        ),
    ),
    (
        "def_test",
        re.compile(
            rf"^\s*def\s+test_(ac_[a-z0-9_]+)\s*\(",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
]


def _def_name_to_ac_id(name: str) -> str:
    """Map test_ac_rel style to AC-REL."""
    body = name.removeprefix("ac_").upper().replace("_", "-")
    return f"AC-{body}" if not body.startswith("AC-") else body


@dataclass
class AcSectionMap:
    found: dict[str, list[int]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    marker_styles: dict[str, str] = field(default_factory=dict)

    @property
    def ac_ids(self) -> set[str]:
        return set(self.found.keys())


def parse_ac_sections(
    script: str,
    must_ids: list[str] | None = None,
) -> AcSectionMap:
    """Extract AC ids and line numbers from script using multiple marker styles."""
    found: dict[str, list[int]] = {}
    styles: dict[str, str] = {}

    for style, pattern in MARKER_PATTERNS:
        for match in pattern.finditer(script):
            raw = match.group(1)
            ac_id = _def_name_to_ac_id(raw) if style == "def_test" else raw.upper()
            if not re.fullmatch(AC_ID_PATTERN, ac_id, re.IGNORECASE):
                ac_id = raw.upper()
            line_no = script[: match.start()].count("\n") + 1
            found.setdefault(ac_id, []).append(line_no)
            if ac_id not in styles:
                styles[ac_id] = style

    must_set = {m.upper() for m in (must_ids or [])}
    missing = sorted(m for m in must_set if m not in {k.upper() for k in found})
    unknown = sorted(
        k for k in found if must_set and k.upper() not in must_set
    )

    return AcSectionMap(
        found=found,
        missing=missing,
        unknown=unknown,
        marker_styles=styles,
    )


def ac_ids_in_script(script: str) -> set[str]:
    return parse_ac_sections(script).ac_ids


def extract_ac_section_body(script: str, ac_id: str) -> str | None:
    """Return lines belonging to one AC section (from marker to next marker)."""
    section_map = parse_ac_sections(script)
    lines = script.splitlines()
    starts = section_map.found.get(ac_id.upper()) or section_map.found.get(ac_id)
    if not starts:
        for key, lnos in section_map.found.items():
            if key.upper() == ac_id.upper():
                starts = lnos
                break
    if not starts:
        return None

    start_line = starts[0] - 1
    all_markers: list[tuple[int, str]] = []
    for aid, lnos in section_map.found.items():
        for ln in lnos:
            all_markers.append((ln, aid))
    all_markers.sort()

    end_line = len(lines)
    for ln, aid in all_markers:
        if ln - 1 > start_line and aid.upper() != ac_id.upper():
            end_line = ln - 1
            break

    return "\n".join(lines[start_line:end_line])


def script_preamble(script: str, first_ac_line: int) -> str:
    """Shared imports/helpers before the first AC marker."""
    lines = script.splitlines()
    idx = max(0, first_ac_line - 1)
    preamble_lines: list[str] = []
    for line in lines[:idx]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
            preamble_lines.append(line)
            continue
        if stripped.startswith(("import ", "from ", "def print_stacktrace")):
            preamble_lines.append(line)
            continue
        if not preamble_lines:
            preamble_lines.append(line)
    return "\n".join(preamble_lines)
