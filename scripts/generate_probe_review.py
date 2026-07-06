#!/usr/bin/env python3
"""Generate probe_review.md skeleton with auto-filled metrics from spec parser artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.infrastructure.shared_memory import SharedMemoryStore  # noqa: E402

PROBE_CHECKLISTS: dict[str, dict[str, list[str]]] = {
    "sympy__sympy-12481": {
        "L1-A": [
            "architecture_hint: guard / minimal_guard",
            "negative_constraints: 禁止重写 Cycle()",
            "repair_goals: 仅 has_dups 守卫层",
            "AC must: 重叠轮换 Permutation([[0,1],[0,1]])",
            "AC should: 泛化 Permutation([[0,1],[0,2]])",
        ],
        "L1-B": ["combinatorics 族 enrichment 可为空或 minimal_guard"],
        "L1-C": ["buggy 代码上 ValueError/AssertionError", "calibration_passed=true"],
        "L1-D": ["search_context 含 repair_goals 与 negative_constraints"],
    },
    "sympy__sympy-11400": {
        "L1-A": [
            "repair_goals 含 _print_sinc + _print_Relational",
            "prerequisite: Relational 先于 sinc",
            "architecture_hint: delegate_ast, neighbor=_print_ITE",
            "negative_constraints: 禁 inline 三元",
        ],
        "L1-B": [
            "missing_handlers 含 _print_Relational",
            "neighbor_reference 指向 _print_ITE",
        ],
        "L1-C": [
            "脚本 AC-REL + AC-SINC 分节",
            "primary_failure_ac_id=AC-REL (buggy)",
            "calibration_passed=true",
        ],
        "L1-D": ["search_context 含 prerequisite 与 delegate 模式"],
    },
    "sympy__sympy-12454": {
        "L1-A": ["co_fix_required 含 hessenberg", "architecture_hint: dimension_clamp"],
        "L1-B": ["co_fix_candidates 含 _eval_is_upper_hessenberg", "ForLoopVisitor: range(i) 未 clamp"],
        "L1-C": ["脚本同时测 is_upper + hessenberg", "calibration_passed=true"],
        "L1-D": ["search_context 含 co_fix_required"],
    },
    "sympy__sympy-11897": {
        "L1-A": [
            "symptom_goals vs repair_goals 分层 (bracket 层)",
            "repair_goals 非 _print_Mul formatter",
            "out_of_scope 含 reporter 草稿错误层",
            "规格长度合理",
        ],
        "L1-B": ["printing 族 enrichment 可选"],
        "L1-C": ["脚本测 Piecewise(Mul) 括号", "calibration_passed=true"],
        "L1-D": ["search_context 症状/修复分层清晰"],
    },
    "sympy__sympy-12171": {
        "L1-A": [
            "neighbor_reference: Hold+doprint",
            "out_of_scope: Float",
            "criterion_role=no_regression_sentinel: Pow",
        ],
        "L1-B": ["printing/mathematica 族 enrichment"],
        "L1-C": ["脚本含 Deriv + Pow 哨兵", "calibration_passed=true"],
        "L1-D": ["search_context 含 neighbor 与 out_of_scope"],
    },
}


def _cb(done: bool) -> str:
    return "[x]" if done else "[ ]"


def _auto_checks(instance_id: str, probe_dir: Path) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    inst_dir = probe_dir / instance_id
    checks["swm_exists"] = (inst_dir / SharedMemoryStore.FILENAME).is_file()
    checks["repo_enrichment_exists"] = (inst_dir / SharedMemoryStore.REPO_ENRICHMENT_FILENAME).is_file()
    checks["execution_evidence_exists"] = (inst_dir / SharedMemoryStore.EXECUTION_EVIDENCE_FILENAME).is_file()
    checks["search_context_exists"] = (inst_dir / SharedMemoryStore.SEARCH_CONTEXT_FILENAME).is_file()
    checks["repro_script_exists"] = (inst_dir / "reproduce_issue.py").is_file()

    spec = None
    if checks["swm_exists"]:
        swm = SharedMemoryStore.read(inst_dir)
        if swm:
            spec = swm.structured_spec
            checks["json_valid"] = True
            checks["has_repair_goals"] = bool(spec.repair_goals)
            checks["has_symptom_goals"] = bool(spec.symptom_goals)
            checks["has_negative"] = bool(spec.negative_constraints)
        else:
            checks["json_valid"] = False
    else:
        checks["json_valid"] = False

    if checks["repro_script_exists"]:
        script = (inst_dir / "reproduce_issue.py").read_text(errors="replace")
        checks["ac_sections"] = bool(re.search(r"---\s*AC-", script, re.I))

    if checks["execution_evidence_exists"]:
        ee = json.loads((inst_dir / SharedMemoryStore.EXECUTION_EVIDENCE_FILENAME).read_text())
        checks["calibration_passed"] = ee.get("calibration_passed", False)

    if spec:
        blob = spec.model_dump_json().lower()
        checks["has_relational"] = "relational" in blob
        checks["co_fix_hessenberg"] = "hessenberg" in " ".join(spec.fix_scope.co_fix_required).lower()
        if spec.execution_evidence:
            checks["ac_rel_first"] = spec.execution_evidence.primary_failure_ac_id == "AC-REL"
        if spec.repo_enrichment:
            checks["missing_relational"] = any("Relational" in h for h in spec.repo_enrichment.missing_handlers)
        if checks.get("search_context_exists"):
            sc = (inst_dir / SharedMemoryStore.SEARCH_CONTEXT_FILENAME).read_text()
            checks["sc_has_repair_goals"] = "Repair Goals" in sc

    return checks


def generate_review(instance_id: str, probe_dir: Path, *, round_no: int = 1, run_status: str = "completed", run_error: str = "") -> str:
    checks = _auto_checks(instance_id, probe_dir)
    cl = PROBE_CHECKLISTS.get(instance_id, {})
    lines = [
        f"# Probe Review: {instance_id}",
        "",
        f"- round: {round_no}",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- run_status: {run_status}",
    ]
    if run_error:
        lines.append(f"- run_error: `{run_error[:500]}`")
    lines.append("")

    for section, key in [("L1-A Issue extraction", "L1-A"), ("L1-B Static enrichment", "L1-B"), ("L1-C Script and dynamic evidence", "L1-C"), ("L1-D Search context", "L1-D")]:
        lines.append(f"## {section}")
        for item in cl.get(key, []):
            auto = False
            il = item.lower()
            if "repair_goals" in il and checks.get("has_repair_goals"): auto = True
            if "symptom" in il and checks.get("has_symptom_goals"): auto = True
            if "negative" in il and checks.get("has_negative"): auto = True
            if "relational" in il and checks.get("has_relational"): auto = True
            if "hessenberg" in il and checks.get("co_fix_hessenberg"): auto = True
            if "missing_handlers" in il and checks.get("missing_relational"): auto = True
            if "ac-" in il and checks.get("ac_sections"): auto = True
            if "calibration_passed" in il and checks.get("calibration_passed"): auto = True
            if "ac-rel" in il and checks.get("ac_rel_first"): auto = True
            if "search_context" in il and checks.get("search_context_exists") and checks.get("sc_has_repair_goals"): auto = True
            if key == "L1-B" and checks.get("repo_enrichment_exists") and "可选" in item: auto = True
            lines.append(f"- {_cb(auto)} {item}")
        lines.append("")

    lines.extend(["## L2 Search injection (manual)", "- [ ] Search round 0 bug_locations 指向 GT", "- [ ] Repair Contract 未被 ver1 覆盖", ""])
    lines.append("## Auto metrics")
    for k in sorted(checks):
        lines.append(f"- {k}: `{checks[k]}`")
    lines.extend(["", "## Notes", "", "_(人工补充)_", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instance-id", action="append", dest="instance_ids")
    parser.add_argument("--probe-dir", type=Path, default=ROOT / "experiment" / "spec_parser_probe")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--run-status", default="completed")
    parser.add_argument("--run-error", default="")
    parser.add_argument("--task-list", type=Path, default=ROOT / "conf" / "lite300_tasks" / "sympy_five_probes.txt")
    args = parser.parse_args()
    ids = args.instance_ids or [ln.strip() for ln in args.task_list.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    args.probe_dir.mkdir(parents=True, exist_ok=True)
    for iid in ids:
        out = args.probe_dir / iid / "probe_review.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(generate_review(iid, args.probe_dir, round_no=args.round, run_status=args.run_status, run_error=args.run_error))
        print(f"Wrote {out}")

if __name__ == "__main__":
    main()
