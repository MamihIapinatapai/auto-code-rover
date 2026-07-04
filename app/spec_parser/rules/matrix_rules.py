"""Matrix-family AST enrichment rules."""

from __future__ import annotations

from pathlib import Path

from app.spec_parser.rules.common_rules import MATRIX_TARGET_FILES
from app.spec_parser.schema import RepoEnrichment
from app.spec_parser.visitors.return_shape import ForLoopVisitor, index_class_methods
from app.task import Task

HESSENBERG_METHODS = ("_eval_is_upper_hessenberg", "is_upper", "_eval_is_lower")


def _resolve_matrix_files(task: Task) -> list[Path]:
    root = Path(task.project_path)
    found: list[Path] = []
    for rel in MATRIX_TARGET_FILES:
        p = root / rel
        if p.is_file():
            found.append(p)
    if not found:
        for p in root.rglob("matrices.py"):
            if "matrices" in str(p):
                found.append(p)
                break
    return found


def enrich(
    task: Task,
    issue_text: str,
    target_files: list[Path] | None = None,
) -> RepoEnrichment:
    files = target_files or _resolve_matrix_files(task)
    co_fix: list[str] = []
    snippets: dict[str, str] = {}

    for fpath in files:
        source = fpath.read_text(errors="replace")
        methods = index_class_methods(source)
        try:
            tree = __import__("ast").parse(source)
        except SyntaxError:
            continue

        unclamped_methods: list[str] = []
        for node in __import__("ast").walk(tree):
            if isinstance(node, __import__("ast").FunctionDef):
                vis = ForLoopVisitor()
                vis.visit(node)
                for loop in vis.loops:
                    if loop.is_unclamped_j_loop and loop.accesses_self_ij:
                        unclamped_methods.append(node.name)
                        snippets[node.name] = "\n".join(
                            source.splitlines()[node.lineno - 1 : node.lineno + 8]
                        )
                        break

        if unclamped_methods:
            for m in HESSENBERG_METHODS:
                if m in methods and m not in co_fix:
                    co_fix.append(m)
            for m in unclamped_methods:
                if m not in co_fix:
                    co_fix.append(m)

    if "is_upper" in issue_text and "_eval_is_upper_hessenberg" not in co_fix:
        co_fix.append("_eval_is_upper_hessenberg")

    return RepoEnrichment(
        target_files=[str(f.relative_to(task.project_path)) for f in files],
        missing_handlers=[],
        co_fix_candidates=sorted(set(co_fix)),
        neighbor_reference=None,
        architecture_pattern="dimension_clamp" if co_fix else "unknown",
        negative_patterns=[],
        search_api_hints=sorted(set(co_fix))[:10],
        evidence_snippets=snippets,
    )
