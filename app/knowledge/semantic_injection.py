"""
Build semantic knowledge prompt sections for agent injection (ver1 / v2.2 pipeline).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from app import config
from app.data_structures import BugLocation
from app.knowledge.sympy_semantic_rules import SemanticRule, select_sympy_rules
from app.knowledge.ver1 import ACR_LOG_PREFIX, ver1_prompt_header
from app.task import Task

SYMPY_PATH_MARKER = "sympy/"

MODULE_FAMILY_MARKERS = {
    "printing": ("printing/", "sympy/printing"),
    "matrices": ("matrices/", "sympy/matrices"),
    "combinatorics": ("combinatorics/", "sympy/combinatorics"),
}


def _is_sympy_task(task: Task) -> bool:
    if hasattr(task, "repo_name") and task.repo_name:
        return "sympy" in task.repo_name.lower() or "sympy" in task.task_id.lower()
    return "sympy" in task.task_id.lower()


def _bug_location_paths(bug_locs: list[BugLocation] | None) -> list[str]:
    if not bug_locs:
        return []
    return [loc.rel_file_path for loc in bug_locs if loc.rel_file_path]


def should_inject_sympy_rules(
    task: Task,
    bug_locs: list[BugLocation] | None = None,
) -> bool:
    """Route: sympy repo/task OR any bug location under sympy/."""
    if _is_sympy_task(task):
        return True
    for path in _bug_location_paths(bug_locs):
        normalized = path.replace("\\", "/")
        if SYMPY_PATH_MARKER in normalized:
            return True
    return False


def detect_module_families(
    file_paths: list[str] | None = None,
    issue_text: str = "",
) -> list[str]:
    """Heuristic module-family detection from paths and issue text."""
    families: list[str] = []
    combined = " ".join(file_paths or []) + " " + issue_text
    normalized = combined.replace("\\", "/").lower()
    for family, markers in MODULE_FAMILY_MARKERS.items():
        if any(m in normalized for m in markers):
            families.append(family)
    if not families and "sympy" in normalized:
        families.append("core")
    return families


def load_fail_to_pass_test_names(task_dir: str | None) -> list[str]:
    """P2: load FAIL_TO_PASS test name list from meta.json (names only, not asserts)."""
    if not task_dir:
        return []
    meta_path = Path(task_dir) / "meta.json"
    if not meta_path.is_file():
        # task_dir may be search subdir; try parent
        meta_path = Path(task_dir).parent / "meta.json"
    if not meta_path.is_file():
        return []
    try:
        data = json.loads(meta_path.read_text())
        names = data.get("FAIL_TO_PASS", [])
        return [str(n) for n in names] if isinstance(names, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def build_sibling_scan_prompt() -> str:
    """Dedicated prompt for step ④ sibling scan LLM call."""
    return (
        "You have already decided bug_locations (or that more context is needed).\n"
        "Now fill ONLY the sibling scan table per MODULE_PATTERN_SCAN.\n"
        "Do NOT change your bug_locations decision.\n"
        "Apply the needs_fix decision tree.\n\n"
        "Output a markdown table with columns:\n"
        "method_or_handler | class | file | anti_pattern_id | safe | needs_fix | "
        "scope_proof | evidence_snippet\n\n"
        "For each row: needs_fix=yes only with scan evidence; needs_fix=no requires scope_proof "
        "when Issue mentions the symptom."
    )


def build_search_final_round_checklist(
    task: Task,
    *,
    bug_loc_paths: list[str] | None = None,
    module_families_detected: list[str] | None = None,
) -> str:
    """Short checklist injected before ANALYZE_AND_SELECT (P0)."""
    if not config.enable_sympy_pipeline_v2:
        return ""

    paths = bug_loc_paths or []
    families = module_families_detected or detect_module_families(
        paths, task.get_issue_statement()
    )

    lines = [
        "=== Final Localization Checklist (authoritative over Issue draft) ===",
        "",
        "A. Module & Layer",
        "□ Identified owning module family (printing/matrices/combinatorics/core/...)?",
        "□ Fix layer = dispatch / policy / formatting / guard — not misaligned?",
        "",
        "B. Sibling Scan (MODULE_PATTERN_SCAN table complete)",
        "□ Every same-class handler with shared anti_pattern_id marked needs_fix=yes?",
        "□ Issue-mentioned but scan-unproven symptoms marked needs_fix=no with scope_proof?",
    ]

    if "printing" in families:
        lines.extend(
            [
                "",
                "C. Neighbor Contract (for NEW or OVERRIDE handlers)",
                "□ neighbor_reference passes eligibility (semantic sibling / parent, same category + layer)?",
                "□ Quoted eligible reference: outer wrapper + join API + bracket policy (if applicable)?",
                "□ spec_source + spec_rationale filled? If issue_example: Issue aligns with neighbor OR no eligible neighbor?",
            ]
        )

    lines.extend(
        [
            "",
            "D. Parent Inheritance Guard",
            "□ Parent Non-Trivial Implementation → default needs_fix=no unless scope_proof documents break?",
        ]
    )

    if "combinatorics" in families:
        lines.append(
            "□ Guard-only fix vs core rewrite — prefer guard narrowing when scan proves downstream OK"
        )

    lines.extend(
        [
            "",
            "E. bug_locations Emission",
            "□ One entry per needs_fix=yes only; empty if more context needed but scan table still filled?",
        ]
    )

    if "printing" in families:
        lines.append("□ neighbor_reference field required when spec_source involves neighbor_contract")

    if "matrices" in families:
        lines.append(
            "□ Symmetric Property Siblings share dimension-clamp anti-pattern — CO_FIX if same AP-*"
        )

    fail_names = load_fail_to_pass_test_names(getattr(task, "output_dir", None))
    if fail_names:
        lines.extend(
            [
                "",
                "F. Scope hint (test names only, not assert bodies):",
                f"□ FAIL_TO_PASS tests: {', '.join(fail_names[:20])}"
                + (" ..." if len(fail_names) > 20 else ""),
            ]
        )

    return "\n".join(lines)


def _format_rules_section(rules: list[SemanticRule], phase: str) -> str:
    blocks: list[str] = [ver1_prompt_header(phase), "", "=== Domain Semantic Knowledge ==="]
    for rule in rules:
        blocks.append(f"[{rule.name}] (scope: {rule.scope})")
        blocks.append(rule.prompt_text)
        blocks.append("")
    return "\n".join(blocks).rstrip()


def _write_injection_metadata(
    task_dir: str | None,
    *,
    phase: str,
    rules: list[SemanticRule],
    paths_triggered: list[str],
    task: Task,
) -> None:
    if not task_dir:
        return
    meta_path = Path(task_dir) / "semantic_injection_ver1.json"
    payload = {
        "version": "ver1.1",
        "phase": phase,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rules_applied": [r.name for r in rules],
        "paths_triggered": paths_triggered,
        "task_id": getattr(task, "task_id", None),
    }
    meta_path.write_text(json.dumps(payload, indent=2))
    logger.info("{} wrote semantic metadata to {}", ACR_LOG_PREFIX, meta_path)


def build_semantic_context_ver1(
    task: Task,
    *,
    bug_locs: list[BugLocation] | None = None,
    phase: str = "patch",
    task_dir: str | None = None,
) -> str | None:
    """
    Build ver1/v2.2 semantic injection text for search, patch, review, or reproducer agents.
    """
    if not config.enable_semantic_injection_ver1:
        return None
    if not should_inject_sympy_rules(task, bug_locs):
        return None

    file_paths = _bug_location_paths(bug_locs)
    issue_text = task.get_issue_statement()
    rules = select_sympy_rules(
        file_paths=file_paths,
        issue_text=issue_text,
        phase=phase,
    )
    if not rules:
        return None

    context = _format_rules_section(rules, phase)

    if phase in ("search", "patch") and config.enable_sympy_pipeline_v2:
        fail_names = load_fail_to_pass_test_names(task_dir)
        if fail_names:
            context += (
                "\n\n=== Scope hint (FAIL_TO_PASS test names only) ===\n"
                + "\n".join(f"- {n}" for n in fail_names[:30])
            )

    _write_injection_metadata(
        task_dir,
        phase=phase,
        rules=rules,
        paths_triggered=file_paths,
        task=task,
    )
    logger.info("{} semantic rules injected ({})", ACR_LOG_PREFIX, phase)
    return context


def build_semantic_context(
    task: Task,
    *,
    bug_locs: list[BugLocation] | None = None,
    phase: str = "patch",
    task_dir: str | None = None,
) -> str | None:
    """Backward-compatible wrapper around ver1/v2.2 injection."""
    return build_semantic_context_ver1(
        task, bug_locs=bug_locs, phase=phase, task_dir=task_dir
    )
