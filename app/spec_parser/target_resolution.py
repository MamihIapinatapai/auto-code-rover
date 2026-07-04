"""Resolve entity queries to candidate source files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.spec_parser.entity_extraction import EntityQuery, EntityQuerySet
from app.spec_parser.symbol_index import SymbolIndex


@dataclass
class FileCandidate:
    rel_path: str
    score: float
    matched_entities: list[str] = field(default_factory=list)


def infer_context_domain(candidates: list[FileCandidate]) -> str:
    if not candidates:
        return ""
    paths = [c.rel_path.replace("\\", "/") for c in candidates[:5]]
    if len(paths) == 1:
        return str(Path(paths[0]).parent).replace("\\", "/")
    parts_list = [p.split("/") for p in paths]
    common: list[str] = []
    for i, seg in enumerate(parts_list[0][:-1]):
        if all(i < len(p) - 1 and p[i] == seg for p in parts_list):
            common.append(seg)
        else:
            break
    return "/".join(common) if common else str(Path(paths[0]).parent).replace("\\", "/")


def _resolve_path(project_path: Path, path_str: str) -> str | None:
    normalized = path_str.replace("\\", "/")
    candidates = [
        project_path / normalized,
        project_path / Path(normalized).name,
    ]
    for p in candidates:
        if p.is_file() and p.suffix == ".py":
            return str(p.relative_to(project_path)).replace("\\", "/")
    return None


def _grep_entity(project_path: Path, entity: EntityQuery) -> list[str]:
    if entity.kind == "class":
        pattern = rf"class\s+{re.escape(entity.name)}\b"
    elif entity.kind in ("method", "api"):
        pattern = rf"def\s+{re.escape(entity.name.split('.')[-1])}\b"
    else:
        return []
    try:
        cp = subprocess.run(
            ["rg", "-l", pattern, str(project_path), "-g", "*.py", "-g", "!*test*"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if cp.returncode not in (0, 1):
        return []
    found: list[str] = []
    for line in cp.stdout.splitlines()[:10]:
        try:
            rel = str(Path(line).relative_to(project_path)).replace("\\", "/")
            if "test" not in rel.lower():
                found.append(rel)
        except ValueError:
            continue
    return found


def resolve_target_files(
    project_path: str,
    entities: EntityQuerySet,
    index: SymbolIndex,
) -> list[FileCandidate]:
    root = Path(project_path)
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}

    def bump(rel: str, weight: float, entity_name: str) -> None:
        rel = rel.replace("\\", "/")
        scores[rel] = scores.get(rel, 0.0) + weight
        matched.setdefault(rel, [])
        if entity_name not in matched[rel]:
            matched[rel].append(entity_name)

    for eq in entities.queries:
        if eq.kind == "file_path":
            resolved = _resolve_path(root, eq.name)
            if resolved:
                bump(resolved, eq.weight * 1.0, eq.name)
            continue

        lookup_names = [eq.name]
        if eq.kind == "class":
            locs = index.classes.get(eq.name, [])
            for loc in locs:
                bump(loc.rel_path, eq.weight * 1.0, eq.name)
            if not locs:
                for rel in _grep_entity(root, eq):
                    bump(rel, eq.weight * 0.7, eq.name)
        elif eq.kind in ("method", "api"):
            short = eq.name.split(".")[-1]
            lookup_names = [eq.name, short]
            for name in lookup_names:
                for loc in index.functions.get(name, []):
                    bump(loc.rel_path, eq.weight * 0.95, eq.name)
            if not any(index.functions.get(n) for n in lookup_names):
                for rel in _grep_entity(root, eq):
                    bump(rel, eq.weight * 0.65, eq.name)

    threshold = config.spec_parser_candidate_score_threshold
    max_k = config.spec_parser_max_resolve_candidates
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    candidates = [
        FileCandidate(rel_path=rel, score=sc, matched_entities=matched.get(rel, []))
        for rel, sc in ranked
        if sc >= threshold
    ][:max_k]
    return candidates
