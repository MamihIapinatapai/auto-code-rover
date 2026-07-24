#!/usr/bin/env python3
"""Aggregate Baseline Lite300 failure root-cause summary for all 300 instances."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from analyze_sympy_failures import (  # noqa: E402
    BUCKETS,
    analyze_localization,
    classify_b_l2_failure,
    classify_layer2,
    extract_gold_files,
    extract_loc_files,
    latest_task_dir,
    read_eval_status,
)
from lite300_instance_utils import repo_from_instance_id  # noqa: E402

SYNC_PREFIX = ROOT / "lite300_output" / "repos"
EXP_PREFIX = ROOT / "experiment" / "deepseek-lite-300" / "repos"
TASK_LIST = ROOT / "conf" / "swe_lite_tasks.txt"
OUT_MD = ROOT / "document" / "baseline300_failure_summary.md"
OUT_JSONL = ROOT / "document" / "baseline300_failure_summary.jsonl"

PATCH_FILE_RE = re.compile(r"diff --git a/(\S+)")
def short_test_name(name: str) -> str:
    """Strip pytest node id to bare test function name."""
    if "::" in name:
        name = name.rsplit("::", 1)[-1]
    if " (" in name:
        name = name.split(" (", 1)[0]
    return name.strip()


MANUAL_REASONS: dict[str, dict[str, str]] = {
    "sympy__sympy-11400": {
        "mechanism": "Incomplete-Generalization",
        "reason": "仅实现 _print_sinc 的 inline 三元，遗漏 _print_Relational 前置依赖，导致 Relational 与 sinc 两项 FAIL_TO_PASS 失败",
    },
    "sympy__sympy-11897": {
        "mechanism": "Issue-Misalignment",
        "reason": "在 _print_Mul 层 bypass fraction 而非修 _needs_mul_brackets，导致 Piecewise 括号断言失败并触发 RecursionError 回归",
    },
    "sympy__sympy-12171": {
        "mechanism": "Issue-Misalignment",
        "reason": "按 Issue 草稿实现 Derivative 且额外 override _print_Float，导致 Hold 契约缺失与 test_Pow 回归",
    },
    "sympy__sympy-12454": {
        "mechanism": "Incomplete-Generalization",
        "reason": "is_upper 修复正确但未同步修 _eval_is_upper_hessenberg，导致 test_hessenberg IndexError",
    },
    "sympy__sympy-12481": {
        "mechanism": "Delegation-Blindness",
        "reason": "has_dups 守卫修对但重写已正确的 Cycle 合成路径，导致 test_args 数学语义错误",
    },
}


@dataclass
class FailureRecord:
    id: str
    repo: str
    stage: str
    root_class: str
    mechanism: str
    reason: str
    fail_to_pass_failed: list[str] = field(default_factory=list)
    pass_to_pass_failed: list[str] = field(default_factory=list)


def load_tasks() -> list[str]:
    return [
        ln.strip()
        for ln in TASK_LIST.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]


def load_resolved_set() -> set[str]:
    resolved: set[str] = set()
    for repo_dir in SYNC_PREFIX.iterdir():
        if not repo_dir.is_dir():
            continue
        report = repo_dir / "report" / "report.json"
        if report.is_file():
            data = json.loads(report.read_text(encoding="utf-8"))
            resolved.update(data.get("resolved", []))
    return resolved


def load_instance_report(repo_dir: Path, instance_id: str) -> dict | None:
    path = repo_dir / "report" / "instances" / f"{instance_id}.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def extract_patch_files(task_dir: Path | None) -> set[str]:
    if task_dir is None:
        return set()
    selected = task_dir / "selected_patch.json"
    if selected.is_file():
        try:
            rel = json.loads(selected.read_text(encoding="utf-8")).get("selected_patch")
            if rel:
                diff_path = task_dir / rel
                if diff_path.is_file():
                    return set(PATCH_FILE_RE.findall(diff_path.read_text(encoding="utf-8", errors="replace")))
        except (json.JSONDecodeError, OSError):
            pass
    for diff in sorted(task_dir.glob("output_*/extracted_patch_*.diff")):
        return set(PATCH_FILE_RE.findall(diff.read_text(encoding="utf-8", errors="replace")))
    return set()


def classify_stage(
    instance_id: str,
    repo_dir: Path,
    exp_dir: Path,
    resolved: bool,
    eval_status,
    task_dir: Path | None,
    bucket: str | None,
) -> str:
    if resolved:
        return "Resolved"
    pred = repo_dir / f"predictions_{instance_id}.json"
    if eval_status.has_log and not eval_status.resolved:
        return "L3-Fail"
    if bucket == "raw_patch_but_unparsed" or (
        bucket == "raw_patch_but_unparsed"
    ):
        return "L2-Unparsed"
    if task_dir is None:
        for base in (repo_dir, exp_dir):
            for b in BUCKETS:
                hits = sorted(base.glob(f"{b}/{instance_id}_*"), reverse=True)
                if hits:
                    if b == "raw_patch_but_unparsed":
                        return "L2-Unparsed"
                    if b == "no_patch":
                        return "L2-NoPatch"
                    if b == "applicable_patch" and not pred.is_file() and not eval_status.has_log:
                        return "L2-Unparsed"
        return "L2-Missing"
    if bucket == "no_patch":
        return "L2-NoPatch"
    if bucket == "raw_patch_but_unparsed":
        return "L2-Unparsed"
    if bucket == "applicable_patch" and not pred.is_file() and not eval_status.has_log:
        return "L2-Unparsed"
    if eval_status.has_log:
        return "L3-Fail"
    if bucket == "applicable_patch":
        return "L2-Unparsed"
    return "L2-Missing"


def infer_mechanism_l3(
    instance_id: str,
    layer2: str,
    ftp_failed: list[str],
    ptp_failed: list[str],
    ftp_success: list[str],
    loc,
    task_dir: Path | None,
    patch_files: set[str],
    gold_files: set[str],
) -> str:
    if instance_id in MANUAL_REASONS:
        return MANUAL_REASONS[instance_id]["mechanism"]

    if layer2 == "A":
        if loc.reason == "wrong_fault_location":
            return "Agent-Drift"
        if loc.reason == "no_bug_location_extracted":
            return "No-Convergence"
        return "Agent-Drift"

    if layer2 == "B":
        return "Parse-Failure"

    if ptp_failed:
        return "Scope-Creep"

    if ftp_success and ftp_failed:
        return "Incomplete-Generalization"

    if gold_files and patch_files and not (gold_files & patch_files):
        return "Issue-Misalignment"

    if task_dir is not None:
        diff_text = ""
        selected = task_dir / "selected_patch.json"
        if selected.is_file():
            try:
                rel = json.loads(selected.read_text(encoding="utf-8")).get("selected_patch")
                if rel and (task_dir / rel).is_file():
                    diff_text = (task_dir / rel).read_text(encoding="utf-8", errors="replace")
            except (json.JSONDecodeError, OSError):
                pass
        if not diff_text:
            for diff in task_dir.glob("output_*/extracted_patch_*.diff"):
                diff_text = diff.read_text(encoding="utf-8", errors="replace")
                break
        if "/printing/" in " ".join(patch_files) or "printing" in instance_id:
            if diff_text and ("return f\"" in diff_text or "return '" in diff_text or "known_functions" in diff_text):
                if "_print(" not in diff_text and "Piecewise" not in diff_text:
                    return "Delegation-Blindness"

    if ftp_failed and len(ftp_failed) >= 2:
        return "Incomplete-Generalization"

    if ftp_failed:
        return "Under-Scope"

    return "Other"


def build_reason_l3(
    instance_id: str,
    mechanism: str,
    root_class: str,
    ftp_failed: list[str],
    ptp_failed: list[str],
    ftp_success: list[str],
    loc,
    eval_status,
    task_dir: Path | None,
    patch_files: set[str],
    gold_files: set[str],
) -> str:
    if instance_id in MANUAL_REASONS:
        return MANUAL_REASONS[instance_id]["reason"]

    ftp_short = [short_test_name(t) for t in ftp_failed]
    ptp_short = [short_test_name(t) for t in ptp_failed]
    ftp_ok_short = [short_test_name(t) for t in ftp_success]
    tests = ", ".join(ftp_short[:3])
    if len(ftp_short) > 3:
        tests += f" 等{len(ftp_short)}项"

    if root_class == "A-Localization":
        if loc.reason == "wrong_fault_location":
            gold = ", ".join(sorted(gold_files)[:2]) or "GT 文件"
            locf = ", ".join(sorted(loc.loc_files)[:2]) or "错误文件"
            return f"定位锚定 {locf} 而非 {gold}，未能进入有效修复路径 [信息不足]"
        if loc.reason == "no_bug_location_extracted":
            return "检索轮次耗尽未提取 bug_locations，三轮 patch 均未产出可应用补丁"
        return "定位不完整或锚定错误模块，导致补丁未触及真实缺陷点"

    if root_class == "B-SyntaxApply":
        if eval_status.apply_failed:
            return "补丁已提交 L3 但 Docker 内 git apply 失败，未能运行隐藏测试"
        if eval_status.syntax_error:
            return "补丁含语法错误或无效 diff，L3 应用阶段被拦截"
        return "补丁无法通过 L2/L3 应用门禁，未能进入有效评测"

    if mechanism == "Scope-Creep":
        ptp = ", ".join(ptp_short[:2])
        if len(ptp_short) > 2:
            ptp += f" 等{len(ptp_short)}项"
        tail = f"，{tests} 仍未修复" if tests else ""
        return f"修复引入 PASS_TO_PASS 回归（{ptp}）{tail}"

    if mechanism == "Incomplete-Generalization":
        if ftp_success and ftp_failed:
            ok = short_test_name(ftp_success[0])
            bad = short_test_name(ftp_failed[0])
            return f"主修复点已通过 {ok}，但未同步修复关联路径，导致 {bad} 仍失败"
        return f"修复范围不完整，遗漏兄弟方法或前置依赖，导致 {tests} FAIL_TO_PASS 失败"

    if mechanism == "Delegation-Blindness":
        return f"未复用模块既有委托/打印链而手写等价逻辑，导致 {tests} 输出契约不匹配"

    if mechanism == "Issue-Misalignment":
        if gold_files and patch_files and not (gold_files & patch_files):
            return f"补丁修改 {', '.join(sorted(patch_files)[:2])} 与 GT 文件无交集，修错代码路径导致 {tests} 失败"
        return f"按 Issue 症状/草稿实现而非仓库惯例，导致 {tests} 断言失败"

    if mechanism == "Under-Scope":
        return f"补丁逻辑不完整或未覆盖全部 FAIL_TO_PASS 场景，导致 {tests} 仍失败"

    if mechanism == "Patch-Overfitting":
        return f"补丁仅满足窄复现但未满足 SWE-bench 宽契约，导致 {tests} 失败"

    if mechanism == "Architecture-Rollback":
        return f"正确架构方案在反馈迭代中被回退为简化实现，导致 {tests} 失败"

    if mechanism == "Agent-Drift":
        return f"检索曾触及相关代码但最终补丁偏离正确修复点，导致 {tests} 失败"

    if ftp_failed:
        return f"L3 隐藏测试未通过：{tests} FAIL_TO_PASS 失败"
    return "L3 评测未 Resolved，具体根因需进一步人工复核 [信息不足]"


def build_reason_l2(stage: str, mechanism: str, loc, l2_failure) -> str:
    if stage == "L2-Missing":
        return "无 applicable_patch 产物且无 prediction，Agent 未完成该题流水线"

    if stage == "L2-NoPatch":
        if loc.reason == "no_bug_location_extracted":
            return "三轮 patch 均未 APPLICABLE，检索未收敛且 bug_locations 为空"
        return "三次 patch 尝试均未产出可应用补丁，归类 no_patch"

    if stage == "L2-Unparsed":
        if l2_failure.l2_reason:
            short = l2_failure.l2_reason.split("；")[0].split("，")[0]
            if len(short) > 58:
                short = short[:55] + "..."
            return f"{short}，未进入 L3"
        return "补丁正文已生成但无法解析为可应用 diff，未进入 L3"

    return "L2 流水线终局失败，未进入 L3 评测 [信息不足]"


def map_root_class(stage: str, layer2: str | None) -> str:
    if stage.startswith("L2"):
        return "Engineering"
    mapping = {"A": "A-Localization", "B": "B-SyntaxApply", "C": "C-LogicAssert"}
    return mapping.get(layer2 or "C", "C-LogicAssert")


def analyze_instance(instance_id: str, resolved_set: set[str]) -> FailureRecord | None:
    repo = repo_from_instance_id(instance_id)
    if repo is None:
        return None

    repo_dir = SYNC_PREFIX / repo
    exp_dir = EXP_PREFIX / repo
    if not repo_dir.is_dir() and not exp_dir.is_dir():
        return FailureRecord(
            id=instance_id,
            repo=repo,
            stage="L2-Missing",
            root_class="Engineering",
            mechanism="No-Convergence",
            reason="无 lite300_output / experiment 目录，Agent 未完成该题流水线",
        )

    search_dir = repo_dir if repo_dir.is_dir() else exp_dir
    eval_status = read_eval_status(search_dir, instance_id)
    task_dir, bucket = latest_task_dir(search_dir, instance_id)
    if task_dir is None and exp_dir.is_dir():
        task_dir, bucket = latest_task_dir(exp_dir, instance_id)

    resolved = instance_id in resolved_set
    if resolved:
        return None

    stage = classify_stage(instance_id, search_dir, exp_dir, resolved, eval_status, task_dir, bucket)
    loc = analyze_localization(search_dir, instance_id, task_dir, bucket)
    layer2 = classify_layer2(instance_id, eval_status, loc, search_dir) if stage == "L3-Fail" else None
    l2_failure = (
        classify_b_l2_failure(instance_id, eval_status, loc, search_dir, task_dir)
        if stage.startswith("L2") or layer2 == "B"
        else None
    )

    inst_report = load_instance_report(search_dir, instance_id)
    if stage == "L3-Fail" and inst_report and inst_report.get("applied"):
        if eval_status.apply_failed or not inst_report.get("parse_ok", True):
            layer2 = "B"
        elif layer2 == "A":
            # Patch reached L3: treat as logic/assert failure unless apply blocked.
            layer2 = "C"
    ftp_failed: list[str] = []
    ptp_failed: list[str] = []
    ftp_success: list[str] = []
    if inst_report:
        ev = inst_report.get("eval_report") or {}
        ftp = ev.get("FAIL_TO_PASS") or {}
        ptp = ev.get("PASS_TO_PASS") or {}
        ftp_failed = list(ftp.get("failure") or [])
        ftp_success = list(ftp.get("success") or [])
        ptp_failed = list(ptp.get("failure") or [])

    patch_files = extract_patch_files(task_dir)
    gold_files = extract_gold_files(task_dir)
    root_class = map_root_class(stage, layer2)

    if stage == "L3-Fail":
        mechanism = infer_mechanism_l3(
            instance_id,
            layer2 or "C",
            ftp_failed,
            ptp_failed,
            ftp_success,
            loc,
            task_dir,
            patch_files,
            gold_files,
        )
        reason = build_reason_l3(
            instance_id,
            mechanism,
            root_class,
            ftp_failed,
            ptp_failed,
            ftp_success,
            loc,
            eval_status,
            task_dir,
            patch_files,
            gold_files,
        )
    else:
        mechanism = "Parse-Failure" if stage == "L2-Unparsed" else "No-Convergence"
        if stage == "L2-Missing":
            mechanism = "No-Convergence"
        reason = build_reason_l2(stage, mechanism, loc, l2_failure)

    if instance_id not in MANUAL_REASONS and len(reason) > 60:
        reason = reason[:57] + "..."

    return FailureRecord(
        id=instance_id,
        repo=repo,
        stage=stage,
        root_class=root_class,
        mechanism=mechanism,
        reason=reason,
        fail_to_pass_failed=ftp_failed,
        pass_to_pass_failed=ptp_failed,
    )


def render_markdown(records: list[FailureRecord], n_pass: int) -> str:
    n_fail = len(records)
    stage_counts = Counter(r.stage for r in records)
    root_counts = Counter(r.root_class for r in records if r.stage == "L3-Fail")
    mech_counts = Counter(r.mechanism for r in records)

    lines = [
        "# Baseline 300 失败案例错因汇总",
        "",
        f"> 生成时间：{date.today().isoformat()}",
        f"> 总题数：300 | 成功：{n_pass} | 失败：{n_fail}",
        f"> 数据来源：`lite300_output/repos/*/report/` + L2 产物目录",
        "",
        "## 统计摘要",
        "",
        "| stage | 数量 |",
        "|-------|------|",
    ]
    for stage in ("L2-Missing", "L2-NoPatch", "L2-Unparsed", "L3-Fail"):
        lines.append(f"| {stage} | {stage_counts.get(stage, 0)} |")

    lines.extend(["", "| root_class (L3 only) | 数量 |", "|----------------------|------|"])
    for rc in ("A-Localization", "B-SyntaxApply", "C-LogicAssert"):
        lines.append(f"| {rc} | {root_counts.get(rc, 0)} |")

    lines.extend(["", "| mechanism | 数量 |", "|-----------|------|"])
    for mech, cnt in mech_counts.most_common():
        lines.append(f"| {mech} | {cnt} |")

    lines.extend(
        [
            "",
            "## 逐案明细",
            "",
            "| ID | stage | root_class | mechanism | 失败原因（一句话） |",
            "|----|-------|------------|-----------|-------------------|",
        ]
    )
    for r in sorted(records, key=lambda x: x.id):
        lines.append(
            f"| {r.id} | {r.stage} | {r.root_class} | {r.mechanism} | {r.reason} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    tasks = load_tasks()
    resolved_set = load_resolved_set()
    records: list[FailureRecord] = []
    for iid in tasks:
        rec = analyze_instance(iid, resolved_set)
        if rec is not None:
            records.append(rec)

    n_pass = len(tasks) - len(records)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_markdown(records, n_pass), encoding="utf-8")

    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda x: x.id):
            f.write(
                json.dumps(
                    {
                        "id": r.id,
                        "repo": r.repo,
                        "stage": r.stage,
                        "root_class": r.root_class,
                        "mechanism": r.mechanism,
                        "reason": r.reason,
                        "fail_to_pass_failed": r.fail_to_pass_failed,
                        "pass_to_pass_failed": r.pass_to_pass_failed,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"Wrote {OUT_MD} ({len(records)} failures, {n_pass} resolved)")
    print(f"Wrote {OUT_JSONL}")
    stage_counts = Counter(r.stage for r in records)
    print("Stage breakdown:", dict(stage_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
