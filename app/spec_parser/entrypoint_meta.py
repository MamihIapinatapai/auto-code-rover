"""Parse packaging metadata for console_scripts / entry points (v3.3.1 Tier1)."""

from __future__ import annotations

import re
from pathlib import Path

from app.spec_parser.schema import AnchorEntrypoint

_CONSOLE_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9_.\-]+)\s*=\s*[\"']?([A-Za-z0-9_.]+:[A-Za-z0-9_]+)[\"']?\s*$"
)


def parse_pyproject_scripts(project_path: str | Path) -> list[AnchorEntrypoint]:
    root = Path(project_path)
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    out: list[AnchorEntrypoint] = []
    section: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        if section in (
            "project.scripts",
            "project.entry-points.console_scripts",
            "tool.poetry.scripts",
        ):
            m = _CONSOLE_LINE_RE.match(stripped)
            if not m:
                continue
            out.append(
                AnchorEntrypoint(
                    kind="console_script",
                    name=m.group(1),
                    target=m.group(2),
                    rel_path="pyproject.toml",
                    evidence=stripped[:120],
                    confidence=0.9,
                )
            )
    return out


def parse_setup_cfg_scripts(project_path: str | Path) -> list[AnchorEntrypoint]:
    root = Path(project_path)
    path = root / "setup.cfg"
    if not path.is_file():
        return []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    out: list[AnchorEntrypoint] = []
    in_console = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_console = stripped.lower() in (
                "[options.entry_points]",
                "[entry_points]",
            ) or "console_scripts" in stripped.lower()
            if stripped.lower() == "console_scripts":
                in_console = True
            continue
        if stripped.lower() == "console_scripts =":
            in_console = True
            continue
        if not in_console:
            continue
        if stripped.startswith("["):
            in_console = False
            continue
        m = _CONSOLE_LINE_RE.match(stripped)
        if m:
            out.append(
                AnchorEntrypoint(
                    kind="console_script",
                    name=m.group(1),
                    target=m.group(2),
                    rel_path="setup.cfg",
                    evidence=stripped[:120],
                    confidence=0.85,
                )
            )
    return out


def collect_entrypoint_meta(project_path: str | Path) -> list[AnchorEntrypoint]:
    """Merge pyproject + setup.cfg; de-dupe by name."""
    items = parse_pyproject_scripts(project_path) + parse_setup_cfg_scripts(project_path)
    seen: set[str] = set()
    out: list[AnchorEntrypoint] = []
    for ep in items:
        key = ep.name or ep.target
        if key in seen:
            continue
        seen.add(key)
        out.append(ep)
    return out
