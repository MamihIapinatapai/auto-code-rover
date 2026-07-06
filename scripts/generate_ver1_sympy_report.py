#!/usr/bin/env python3
"""Generate ver1 vs baseline SymPy evaluation comparison report."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_REPORT_DIR = ROOT / "lite300_output/repos/sympy/report/instances"
VER1_REPORT_DIR = ROOT / "lite300_output_ver1/repos/sympy/report/instances"
BASELINE_EVAL_DIR = ROOT / "lite300_output/repos/sympy/eval_logs"
VER1_EVAL_DIR = ROOT / "lite300_output_ver1/repos/sympy/eval_logs"
OUTPUT_PATH = ROOT / "document/output_analysis/sympy/sympy_ver1_run_report.md"

C_CLASS_CASES = [
    "sympy__sympy-11400",
    "sympy__sympy-11897",
    "sympy__sympy-12171",
    "sympy__sympy-12454",
    "sympy__sympy-12481",
]


def load_reports(report_dir: Path) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    if not report_dir.is_dir():
        return reports
    for path in sorted(report_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        iid = data.get("instance_id") or path.stem
        reports[iid] = data
    return reports


def is_resolved(report: dict) -> bool:
    status = report.get("resolution_status", "")
    if status == "RESOLVED_YES":
        return True
    if status == "RESOLVED_NO":
        return False
    eval_report = report.get("eval_report") or {}
    f2p = eval_report.get("FAIL_TO_PASS") or {}
    failures = f2p.get("failure") or []
    return len(failures) == 0 and bool(f2p.get("success"))


def extract_error_signature(eval_log_dir: Path, instance_id: str) -> str:
    if not eval_log_dir.is_dir():
        return "no eval log dir"
    logs = list(eval_log_dir.glob(f"{instance_id}.*.eval.log"))
    if not logs:
        return "no eval log"
    text = logs[0].read_text(encoding="utf-8", errors="replace")
    if "RecursionError" in text:
        return "RecursionError"
    if "IndexError" in text:
        return "IndexError"
    if "TypeError" in text:
        return "TypeError"
    if "AssertionError" in text:
        m = re.search(r"AssertionError[^\n]*", text)
        return m.group(0) if m else "AssertionError"
    if "passed" in text.lower() and "failed" not in text.lower():
        return "passed"
    return "other/unknown"


def main() -> int:
    baseline = load_reports(BASELINE_REPORT_DIR)
    ver1 = load_reports(VER1_REPORT_DIR)

    all_ids = sorted(set(baseline) | set(ver1))
    to_resolved: list[str] = []
    to_unresolved: list[str] = []
    unchanged_resolved: list[str] = []
    unchanged_unresolved: list[str] = []

    for iid in all_ids:
        b_res = is_resolved(baseline[iid]) if iid in baseline else None
        v_res = is_resolved(ver1[iid]) if iid in ver1 else None
        if b_res is False and v_res is True:
            to_resolved.append(iid)
        elif b_res is True and v_res is False:
            to_unresolved.append(iid)
        elif v_res is True:
            unchanged_resolved.append(iid)
        elif v_res is False:
            unchanged_unresolved.append(iid)

    b_rate = (
        sum(is_resolved(r) for r in baseline.values()) / len(baseline) * 100
        if baseline
        else 0.0
    )
    v_rate = (
        sum(is_resolved(r) for r in ver1.values()) / len(ver1) * 100 if ver1 else 0.0
    )

    lines: list[str] = [
        "# SymPy ver1 运行报告",
        "",
        f"> 生成时间: {datetime.now(timezone.utc).isoformat()}",
        f"> 版本: **ver1** (`[AutoCodeRover-ver1]`)",
        "",
        "## 汇总",
        "",
        f"| 指标 | Baseline | ver1 |",
        f"|------|----------|------|",
        f"| Instance 数 | {len(baseline)} | {len(ver1)} |",
        f"| Resolved 率 | {b_rate:.1f}% | {v_rate:.1f}% |",
        f"| Unresolved→Resolved | — | {len(to_resolved)} |",
        f"| Resolved→Unresolved | — | {len(to_unresolved)} |",
        "",
        "## 状态转移",
        "",
        "### Unresolved → Resolved",
        "",
    ]
    lines.extend(f"- {iid}" for iid in to_resolved) or lines.append("- _无_")
    lines.extend(["", "### Resolved → Unresolved", ""])
    lines.extend(f"- {iid}" for iid in to_unresolved) or lines.append("- _无_")

    lines.extend(["", "## 5 个 C 类典型 Case 专项", ""])
    lines.append("| Instance | Baseline | ver1 | Baseline 错误 | ver1 错误 | 变化 |")
    lines.append("|----------|----------|------|---------------|-----------|------|")
    for iid in C_CLASS_CASES:
        b_st = "Resolved" if iid in baseline and is_resolved(baseline[iid]) else "Unresolved"
        v_st = "Resolved" if iid in ver1 and is_resolved(ver1[iid]) else "Unresolved"
        b_err = extract_error_signature(BASELINE_EVAL_DIR, iid)
        v_err = extract_error_signature(VER1_EVAL_DIR, iid)
        change = "—"
        if b_st != v_st:
            change = f"{b_st}→{v_st}"
        elif b_err != v_err:
            change = f"traceback: {b_err}→{v_err}"
        else:
            change = "unchanged"
        lines.append(f"| {iid} | {b_st} | {v_st} | {b_err} | {v_err} | {change} |")

    if not ver1:
        lines.extend(
            [
                "",
                "## 说明",
                "",
                "ver1 评测结果目录为空。请先运行:",
                "",
                "```bash",
                "bash scripts/run_sympy_ver1_eval.sh",
                "```",
            ]
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
