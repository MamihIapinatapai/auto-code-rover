"""ScriptAnchor Tier1: Issue-driven static contract anchoring (v3.3.1)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from loguru import logger

from app import config
from app.search.search_utils import is_test_file
from app.spec_parser.entity_extraction import collect_entities
from app.spec_parser.entrypoint_meta import collect_entrypoint_meta
from app.spec_parser.schema import (
    AnchorEntrypoint,
    AnchorSymbol,
    ScriptAnchor,
    StructuredSpecification,
)
from app.spec_parser.symbol_index import SymbolIndex, build_symbol_index
from app.spec_parser.target_resolution import resolve_target_files

_CLI_ISSUE_RE = re.compile(r"\b(cli|command[\s-]?line|click|console)\b", re.I)
_HTTP_ISSUE_RE = re.compile(r"\b(web|http|/api/|endpoint|fastapi|flask|starlette)\b", re.I)
_IDENT_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]{1,40})\b")
_DECORATOR_CLICK_RE = re.compile(r"@(?:click\.)?(?:command|group)\b")
_DECORATOR_ROUTE_RE = re.compile(
    r"@(?:app|router)\.(?:route|get|post|put|delete|patch)\b|@APIRouter\b"
)


def format_ast_signature(node: ast.AST) -> str:
    """Return e.g. '(self, *, recipe=()) -> Any' without evaluating defaults."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return ""
    args = node.args
    parts: list[str] = []

    def _fmt_arg(arg: ast.arg, default: ast.expr | None = None) -> str:
        name = arg.arg
        if default is None:
            return name
        try:
            d = ast.unparse(default)
            if len(d) > 40:
                d = "..."
        except Exception:  # noqa: BLE001
            d = "..."
        return f"{name}={d}"

    pos = list(args.posonlyargs) + list(args.args)
    defaults = list(args.defaults)
    # align defaults to the end of pos args
    default_offset = len(pos) - len(defaults)
    for i, arg in enumerate(pos):
        default = defaults[i - default_offset] if i >= default_offset else None
        parts.append(_fmt_arg(arg, default))
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(_fmt_arg(arg, default))
    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")
    ret = ""
    if node.returns is not None:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:  # noqa: BLE001
            ret = ""
    return f"({', '.join(parts)}){ret}"


def _doc_head(node: ast.AST) -> str:
    doc = ast.get_docstring(node) or ""
    line = doc.strip().splitlines()[0] if doc.strip() else ""
    return line[:120]


def _extract_def_from_file(
    project_path: Path,
    rel_path: str,
    symbol_name: str,
) -> tuple[str, bool, str, int | None, str]:
    """Return signature_ast, is_async, docstring_head, lineno, kind."""
    abs_path = project_path / rel_path
    try:
        source = abs_path.read_text(errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return "", False, "", None, "unknown"

    short = symbol_name.split(".")[-1]
    class_name = symbol_name.split(".")[0] if "." in symbol_name else ""

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == short and "." not in symbol_name:
            # prefer __init__ signature for classes
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                    return (
                        format_ast_signature(item),
                        isinstance(item, ast.AsyncFunctionDef),
                        _doc_head(node) or _doc_head(item),
                        item.lineno,
                        "class",
                    )
            return "", False, _doc_head(node), node.lineno, "class"
        if isinstance(node, ast.ClassDef):
            if class_name and node.name != class_name and "." in symbol_name:
                continue
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == short:
                    return (
                        format_ast_signature(item),
                        isinstance(item, ast.AsyncFunctionDef),
                        _doc_head(item),
                        item.lineno,
                        "method",
                    )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == short:
            return (
                format_ast_signature(node),
                isinstance(node, ast.AsyncFunctionDef),
                _doc_head(node),
                node.lineno,
                "function",
            )
    return "", False, "", None, "unknown"


def _scan_decorators_in_files(
    project_path: Path, rel_paths: list[str]
) -> list[AnchorEntrypoint]:
    if not getattr(config, "spec_parser_anchor_scan_decorators", True):
        return []
    out: list[AnchorEntrypoint] = []
    for rel in rel_paths[:20]:
        if is_test_file(rel):
            continue
        abs_path = project_path / rel
        try:
            text = abs_path.read_text(errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines()[:400], 1):
            if _DECORATOR_CLICK_RE.search(line):
                out.append(
                    AnchorEntrypoint(
                        kind="click_command",
                        name=f"line{i}",
                        target="",
                        rel_path=rel,
                        evidence=line.strip()[:120],
                        confidence=0.55,
                    )
                )
            if _DECORATOR_ROUTE_RE.search(line):
                out.append(
                    AnchorEntrypoint(
                        kind="flask_route"
                        if "route" in line
                        else "fastapi_route",
                        name=f"line{i}",
                        target="",
                        rel_path=rel,
                        evidence=line.strip()[:120],
                        confidence=0.5,
                    )
                )
    return out[:8]


def _seed_names(issue_text: str, spec: StructuredSpecification) -> list[str]:
    names: list[str] = []
    for ac in spec.acceptance_criteria:
        if ac.covers_entity:
            names.append(ac.covers_entity.strip())
        for m in _IDENT_RE.findall(ac.observable or ""):
            names.append(m)
    for m in _IDENT_RE.findall(issue_text[:6000]):
        names.append(m)
    # grounded: must appear in issue or AC text
    blob = (issue_text + "\n" + " ".join(ac.observable for ac in spec.acceptance_criteria)).lower()
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        key = n.lower()
        if key in seen or len(n) < 2:
            continue
        if n.lower() not in blob and n not in issue_text:
            continue
        seen.add(key)
        out.append(n)
    return out[:40]


def build_tier1(
    *,
    project_path: str,
    issue_text: str,
    spec: StructuredSpecification,
    task_id: str = "",
    package_roots: list[str] | None = None,
) -> ScriptAnchor:
    """
    Build ScriptAnchor Tier1.

    Evidence (B1): v3 disables repo_enrichment — always call build_symbol_index here.
    """
    root = Path(project_path)
    errors: list[str] = []
    max_sym = int(getattr(config, "spec_parser_anchor_max_symbols", 12) or 12)
    max_ep = int(getattr(config, "spec_parser_anchor_max_entrypoints", 8) or 8)

    try:
        index: SymbolIndex = build_symbol_index(project_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("ScriptAnchor index failed: {}", exc)
        errors.append(f"index_failed:{type(exc).__name__}")
        index = SymbolIndex()

    entities = collect_entities(issue_text, spec, index)
    # merge seed names into locate via index lookup
    seed_names = _seed_names(issue_text, spec)

    symbols: list[AnchorSymbol] = []
    missing: list[str] = []
    located_files: list[str] = []

    # From entity resolution
    try:
        candidates = resolve_target_files(project_path, entities, index, draft=spec)
        located_files.extend([c.rel_path for c in candidates[:15]])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"resolve_failed:{type(exc).__name__}")
        candidates = []

    # Symbol hits from index for entity + seed names
    name_hits: dict[str, list[tuple[str, int, float]]] = {}
    for eq in entities.queries:
        name = eq.name
        locs = []
        if eq.kind == "class":
            locs = index.classes.get(name, [])
        else:
            locs = index.functions.get(name, []) or index.functions.get(
                name.split(".")[-1], []
            )
        for loc in locs:
            if is_test_file(loc.rel_path):
                continue
            name_hits.setdefault(name, []).append(
                (loc.rel_path, loc.lineno, 1.0 if eq.is_primary else 0.85)
            )

    for name in seed_names:
        if name in name_hits:
            continue
        locs = index.classes.get(name, []) or index.functions.get(name, [])
        for loc in locs:
            if is_test_file(loc.rel_path):
                continue
            name_hits.setdefault(name, []).append((loc.rel_path, loc.lineno, 0.7))

    for name, hits in name_hits.items():
        # unique paths
        paths = []
        seen_p: set[str] = set()
        for rel, lineno, _w in sorted(hits, key=lambda x: -x[2]):
            if rel in seen_p:
                continue
            seen_p.add(rel)
            paths.append((rel, lineno))
        if not paths:
            missing.append(name)
            continue
        primary_rel, primary_lineno = paths[0]
        sig, is_async, doc, lineno, kind = _extract_def_from_file(
            root, primary_rel, name
        )
        n_hits = len(paths)
        if n_hits == 1 and sig:
            conf = 0.85
            ambiguous = False
        elif n_hits == 1:
            conf = 0.55
            ambiguous = False
        else:
            conf = min(0.6, 0.5)
            ambiguous = True
        if not sig:
            conf = min(conf, 0.4)
        symbols.append(
            AnchorSymbol(
                name=name if kind != "method" or "." in name else (
                    f"{name}" if kind == "class" else name
                ),
                kind=kind,
                rel_path=primary_rel,
                lineno=lineno or primary_lineno,
                signature_ast=sig,
                is_async=is_async,
                docstring_head=doc,
                source="issue",
                confidence=conf,
                ambiguous=ambiguous,
                alternate_paths=[p for p, _ in paths[1:3]],
            )
        )
        if primary_rel not in located_files:
            located_files.append(primary_rel)

    for name in seed_names:
        if name not in name_hits and name not in {s.name.split(".")[-1] for s in symbols}:
            if name[0].isupper() and name.lower() in issue_text.lower():
                missing.append(name)

    # Entrypoints
    entrypoints = collect_entrypoint_meta(project_path)
    if not entrypoints:
        errors.append("no_packaging_metadata")
    entrypoints.extend(_scan_decorators_in_files(root, located_files))
    entrypoints = entrypoints[:max_ep]
    symbols = symbols[:max_sym]

    layer_hints = {
        "library": "present" if symbols else "unknown",
        "cli": "absent",
        "http": "absent",
    }
    if any(ep.kind in ("console_script", "click_command") for ep in entrypoints):
        layer_hints["cli"] = "present"
    elif _CLI_ISSUE_RE.search(issue_text):
        layer_hints["cli"] = "unknown"
    if any("route" in ep.kind for ep in entrypoints):
        layer_hints["http"] = "present"
    elif _HTTP_ISSUE_RE.search(issue_text):
        layer_hints["http"] = "unknown"

    tier1_ok = bool(symbols or entrypoints)
    return ScriptAnchor(
        task_id=task_id,
        parser_version="3.3.1",
        package_roots=list(package_roots or []),
        symbols=symbols,
        entrypoints=entrypoints,
        layer_hints=layer_hints,
        missing_issue_symbols=sorted(set(missing))[:20],
        build_errors=errors,
        tier1_ok=tier1_ok,
    )


def format_anchor_for_prompt(anchor: ScriptAnchor, *, max_chars: int | None = None) -> str:
    """Format ScriptAnchor for generator/reviewer. B2: low confidence omits signatures."""
    max_chars = max_chars or int(
        getattr(config, "spec_parser_anchor_prompt_max_chars", 3500) or 3500
    )
    lines = [
        "## ScriptAnchor (repo contract — do NOT invent params/entries absent here)",
        "Issue behavior/expected values OVERRIDE Anchor when they conflict.",
        "### Symbols (prefer these signatures when confidence>=0.5 and not ambiguous)",
    ]
    # sort by confidence desc
    for sym in sorted(anchor.symbols, key=lambda s: -s.confidence):
        amb = " AMBIGUOUS" if sym.ambiguous else ""
        head = (
            f"- {sym.name} ({sym.kind}) path={sym.rel_path}"
            f"{':' + str(sym.lineno) if sym.lineno else ''} "
            f"conf={sym.confidence:.2f}{amb}"
        )
        lines.append(head)
        if sym.alternate_paths:
            lines.append(f"  alternates: {', '.join(sym.alternate_paths)}")
        # B2: omit detailed signatures for low confidence
        if sym.confidence < 0.5 or sym.ambiguous:
            lines.append("  signature: (omitted — low confidence / ambiguous; prefer Issue code)")
        else:
            sig = sym.signature_runtime or sym.signature_ast
            if sig:
                label = "runtime" if sym.signature_runtime else "AST"
                lines.append(f"  {label}: {sig}")
            if sym.docstring_runtime or sym.docstring_head:
                lines.append(
                    f"  doc: {(sym.docstring_runtime or sym.docstring_head)[:100]}"
                )
    if not anchor.symbols:
        lines.append("- (none located)")

    lines.append("### Entrypoints")
    for ep in anchor.entrypoints:
        lines.append(
            f"- {ep.kind}: {ep.name} = {ep.target} ({ep.rel_path}) :: {ep.evidence[:80]}"
        )
    if not anchor.entrypoints:
        lines.append("- (none)")

    lines.append("### Layer hints")
    lines.append(
        "- "
        + " | ".join(f"{k}: {v}" for k, v in sorted(anchor.layer_hints.items()))
    )
    if anchor.missing_issue_symbols:
        lines.append(
            "### Missing issue symbols\n- "
            + ", ".join(anchor.missing_issue_symbols[:12])
        )
    lines.append(
        "Rules:\n"
        "- Call parameters SHOULD match listed signatures when conf>=0.5 and not ambiguous.\n"
        "- If Issue requires CLI/Web and layer is present, exercise entrypoints "
        "(CliRunner/subprocess/HTTP client), not only lower-level APIs.\n"
        "- Do not copy assertions from test files."
    )
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n... (anchor truncated)"
    return text


def detect_layer_gaps(issue_text: str, anchor: ScriptAnchor) -> list[str]:
    """Return LAYER_GAP_CLI / LAYER_GAP_HTTP when Issue implies layer but hint != present."""
    gaps: list[str] = []
    if _CLI_ISSUE_RE.search(issue_text) and anchor.layer_hints.get("cli") != "present":
        gaps.append("LAYER_GAP_CLI")
    if _HTTP_ISSUE_RE.search(issue_text) and anchor.layer_hints.get("http") != "present":
        gaps.append("LAYER_GAP_HTTP")
    return gaps


def persist_anchor(output_dir: Path, anchor: ScriptAnchor) -> Path:
    path = output_dir / "script_anchor.json"
    path.write_text(anchor.model_dump_json(indent=2))
    return path
