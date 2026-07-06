"""Resolve entity queries to candidate source files."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.spec_parser.entity_extraction import EntityQuery, EntityQuerySet, infer_primary_class
from app.spec_parser.entity_policy import is_ambiguous_method
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
        short = entity.name.split(".")[-1]
        if "." in entity.name:
            cls, meth = entity.name.rsplit(".", 1)
            pattern = rf"class\s+{re.escape(cls)}[\s\S]*?def\s+{re.escape(meth)}\b"
            # fallback to simple def grep below for rg -l we use class first
            pattern = rf"def\s+{re.escape(meth)}\b"
        else:
            pattern = rf"def\s+{re.escape(short)}\b"
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


def apply_cooccurrence_bonus(
    candidates: list[FileCandidate],
    primary_class: str | None,
    index: SymbolIndex,
) -> list[FileCandidate]:
    if not primary_class or primary_class not in index.classes:
        return candidates
    bonus = config.spec_parser_cooccurrence_bonus
    class_paths = {loc.rel_path for loc in index.classes[primary_class]}
    boosted: list[FileCandidate] = []
    for c in candidates:
        score = c.score
        if c.rel_path in class_paths:
            score += bonus
            qual = f"{primary_class}.__init__"
            if any(
                loc.rel_path == c.rel_path for loc in index.functions.get(qual, [])
            ):
                score += bonus * 0.5
        boosted.append(
            FileCandidate(
                rel_path=c.rel_path,
                score=score,
                matched_entities=list(c.matched_entities),
            )
        )
    return sorted(boosted, key=lambda x: -x.score)


def resolve_target_files(
    project_path: str,
    entities: EntityQuerySet,
    index: SymbolIndex,
    draft=None,
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
        weight = eq.weight
        if eq.is_primary:
            weight *= config.spec_parser_primary_entity_boost

        if eq.kind == "file_path":
            resolved = _resolve_path(root, eq.name)
            if resolved:
                bump(resolved, weight * 1.0, eq.name)
            continue

        if eq.kind == "method" and "." in eq.name:
            cls, _meth = eq.name.rsplit(".", 1)
            for loc in index.functions.get(eq.name, []):
                bump(loc.rel_path, weight * 1.0, eq.name)
            for loc in index.classes.get(cls, []):
                bump(loc.rel_path, weight * 0.4, f"{cls}@class")
            if not index.functions.get(eq.name):
                for rel in _grep_entity(root, eq):
                    bump(rel, weight * 0.75, eq.name)
            continue

        if eq.kind == "method" and is_ambiguous_method(eq.name):
            continue

        if eq.kind == "class":
            locs = index.classes.get(eq.name, [])
            for loc in locs:
                bump(loc.rel_path, weight * 1.0, eq.name)
            if not locs:
                for rel in _grep_entity(root, eq):
                    bump(rel, weight * 0.7, eq.name)
        elif eq.kind in ("method", "api"):
            short = eq.name.split(".")[-1]
            lookup_names = [eq.name, short]
            hit = False
            for name in lookup_names:
                for loc in index.functions.get(name, []):
                    bump(loc.rel_path, weight * 0.95, eq.name)
                    hit = True
            if not hit:
                for rel in _grep_entity(root, eq):
                    bump(rel, weight * 0.65, eq.name)

    threshold = config.spec_parser_candidate_score_threshold
    max_k = config.spec_parser_max_resolve_candidates
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    candidates = [
        FileCandidate(rel_path=rel, score=sc, matched_entities=matched.get(rel, []))
        for rel, sc in ranked
        if sc >= threshold
    ][:max_k]

    primary = infer_primary_class(entities, draft) if draft is not None else None
    return apply_cooccurrence_bonus(candidates, primary, index)
