#!/usr/bin/env python3
"""Classify SymPy SWE-bench Lite300 evaluation failures into a two-layer funnel."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lite300_instance_utils import instance_id_from_task_dir  # noqa: E402

BUCKETS = ("applicable_patch", "raw_patch_but_unparsed", "no_patch")
GOLD_FILE_RE = re.compile(r"diff --git a/(\S+)")
SYNTAX_ERROR_RE = re.compile(r"\b(SyntaxError|IndentationError)\b")
APPLY_FAIL_RE = re.compile(
    r"Apply patch failed \(pred\)|error: patch failed", re.IGNORECASE
)


@dataclass
class EvalStatus:
    has_log: bool = False
    resolved: bool = False
    apply_failed: bool = False
    syntax_error: bool = False
    patch_applied: bool = False
    tests_failed: bool = False
    log_path: str | None = None
    traceback: str | None = None


@dataclass
class LocalizationInfo:
    has_bug_location: bool = False
    loc_files: list[str] = field(default_factory=list)
    gold_files: list[str] = field(default_factory=list)
    bucket: str | None = None
    task_dir: str | None = None
    reason: str = ""


@dataclass
class L2FailureInfo:
    l2_category: str = ""
    l2_subtype: str = ""
    l2_reason: str = ""


L2_SUBTYPE_META: dict[str, dict[str, str]] = {
    "B1_patch_unparsed": {
        "label": "B1 补丁无法解析",
        "summary": "LLM 输出了 patch_raw，但补丁提取器无法生成有效 unified diff",
    },
    "B2_patch_not_submitted": {
        "label": "B2 补丁未通过 L2 提交门禁",
        "summary": "曾有 applicable_patch 产物，但 gap-fill 重跑后仍无法写入 predictions，未进入 L3",
    },
    "B3_l3_apply_failed": {
        "label": "B3 L3 补丁应用失败",
        "summary": "补丁已提交 L3 评测，但 Docker 内 git apply 失败",
    },
}


@dataclass
class InstanceRecord:
    instance_id: str
    layer1: str  # resolved | unresolved
    layer2: str | None = None  # A | B | C
    l3_evaluated: bool = False
    pipeline_stage: str = "L2_terminal"  # L3 | L2_terminal
    l2_failure: L2FailureInfo = field(default_factory=L2FailureInfo)
    eval_status: EvalStatus = field(default_factory=EvalStatus)
    localization: LocalizationInfo = field(default_factory=LocalizationInfo)
    paths: dict[str, str | list[str] | None] = field(default_factory=dict)


def rel_to_root(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def discover_instances_from_artifacts(repo_dir: Path) -> list[str]:
    """Fallback: instances with L3 eval logs and/or SWE-bench predictions."""
    ids: set[str] = set()
    for pred in repo_dir.glob("predictions_sympy__*.json"):
        ids.add(pred.stem.replace("predictions_", ""))
    eval_dir = repo_dir / "eval_logs"
    if eval_dir.is_dir():
        for log in eval_dir.glob("*.eval.log"):
            ids.add(log.name.split(".")[0])
    return sorted(i for i in ids if i.startswith("sympy__"))


def discover_instances(
    repo_dir: Path, task_list: Path | None = None
) -> list[str]:
    """Full SymPy set from task list; fallback to L3 artifact scan."""
    if task_list is None:
        task_list = ROOT / "conf" / "lite300_tasks" / "sympy.txt"
    if task_list.is_file():
        ids = [
            ln.strip()
            for ln in task_list.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        for instance_id in ids:
            task_dir, _ = latest_task_dir(repo_dir, instance_id)
            if task_dir is None:
                print(
                    f"WARNING: no task dir for {instance_id} under {repo_dir}",
                    file=sys.stderr,
                )
        return ids
    return discover_instances_from_artifacts(repo_dir)


def latest_task_dir(repo_dir: Path, instance_id: str) -> tuple[Path | None, str | None]:
    best: Path | None = None
    best_bucket: str | None = None
    for bucket in BUCKETS:
        for task_dir in sorted(
            repo_dir.glob(f"{bucket}/{instance_id}_*"), reverse=True
        ):
            if task_dir.is_dir():
                if best is None or task_dir.name > best.name:
                    best = task_dir
                    best_bucket = bucket
    return best, best_bucket


def read_eval_status(repo_dir: Path, instance_id: str) -> EvalStatus:
    logs = sorted((repo_dir / "eval_logs").glob(f"{instance_id}.*.eval.log"))
    if not logs:
        return EvalStatus()
    log_path = logs[0]
    text = log_path.read_text(encoding="utf-8", errors="replace")
    status = EvalStatus(
        has_log=True,
        resolved=">>>>> All Tests Passed" in text,
        apply_failed=bool(APPLY_FAIL_RE.search(text)),
        syntax_error=bool(SYNTAX_ERROR_RE.search(text)),
        patch_applied="Apply patch successful (pred)" in text,
        tests_failed=">>>>> Some Tests Failed" in text,
        log_path=rel_to_root(log_path),
    )
    tb_match = re.search(
        r"Traceback \(most recent call last\):.*?(?=\n={5,}|\n>>>>> Some Tests Failed|\Z)",
        text,
        re.DOTALL,
    )
    if tb_match:
        status.traceback = tb_match.group(0).strip()
    return status


def extract_gold_files(task_dir: Path | None) -> set[str]:
    if task_dir is None:
        return set()
    meta_path = task_dir / "meta.json"
    if meta_path.is_file():
        patch = json.loads(meta_path.read_text(encoding="utf-8")).get("task_info", {}).get(
            "patch", ""
        )
        if patch:
            return set(GOLD_FILE_RE.findall(patch))
    dev_patch = task_dir / "developer_patch.diff"
    if dev_patch.is_file():
        return set(GOLD_FILE_RE.findall(dev_patch.read_text(encoding="utf-8", errors="replace")))
    return set()


def extract_loc_files(task_dir: Path | None) -> set[str]:
    if task_dir is None:
        return set()
    files: set[str] = set()
    for bug_json in sorted(task_dir.glob("output_*/search/bug_locations_after_process.json")):
        try:
            data = json.loads(bug_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            f = item.get("rel_file_path") or item.get("file") or item.get("file_path")
            if f:
                files.add(str(f))
    info_log = task_dir / "info.log"
    if info_log.is_file():
        info = info_log.read_text(encoding="utf-8", errors="replace")
        if "Bug location extracted successfully" in info:
            files.update(re.findall(r"<file>([^<]+)</file>", info))
    return files


def patch_has_syntax_error(task_dir: Path | None) -> bool:
    """Heuristic syntax check for cases without L3 eval. Partial diffs are not valid modules,
    so this only flags obvious issues (e.g. empty patch or non-Python garbage)."""
    if task_dir is None:
        return False
    selected = task_dir / "selected_patch.json"
    if not selected.is_file():
        return False
    try:
        rel = json.loads(selected.read_text(encoding="utf-8")).get("selected_patch", "")
    except (json.JSONDecodeError, OSError):
        return False
    if not rel:
        return False
    patch_path = task_dir / rel
    if not patch_path.is_file():
        return False
    diff = patch_path.read_text(encoding="utf-8", errors="replace")
    if not diff.strip():
        return True
    # If the diff adds lines containing explicit SyntaxError markers from failed generation.
    return bool(re.search(r"^\+\s*SyntaxError", diff, re.MULTILINE))


def analyze_localization(
    repo_dir: Path, instance_id: str, task_dir: Path | None, bucket: str | None
) -> LocalizationInfo:
    info = LocalizationInfo(bucket=bucket, task_dir=rel_to_root(task_dir))
    if task_dir is None:
        info.reason = "no_task_dir"
        return info

    gold = extract_gold_files(task_dir)
    loc = extract_loc_files(task_dir)
    info.gold_files = sorted(gold)
    info.loc_files = sorted(loc)

    info_log = task_dir / "info.log"
    has_success_line = False
    if info_log.is_file():
        has_success_line = "Bug location extracted successfully" in info_log.read_text(
            encoding="utf-8", errors="replace"
        )
    info.has_bug_location = has_success_line and bool(loc)

    if bucket == "no_patch":
        info.reason = "no_patch_bucket"
    elif not has_success_line and not loc:
        info.reason = "no_bug_location_extracted"
    elif gold and not (gold & loc):
        info.reason = "wrong_fault_location"
    elif info.has_bug_location:
        info.reason = "localization_ok"
    else:
        info.reason = "localization_incomplete"

    # Also consider raw_patch bucket without prediction as B, handled in classify_layer2
    if bucket == "raw_patch_but_unparsed":
        pred = repo_dir / f"predictions_{instance_id}.json"
        eval_logs = list((repo_dir / "eval_logs").glob(f"{instance_id}.*.eval.log"))
        if not pred.is_file() or not eval_logs:
            info.reason = "raw_patch_unparsed_no_eval"

    return info


def classify_layer2(
    instance_id: str,
    eval_status: EvalStatus,
    loc: LocalizationInfo,
    repo_dir: Path,
) -> str:
    pred_path = repo_dir / f"predictions_{instance_id}.json"

    # B class — patch never applied or syntax blocked apply
    if loc.bucket == "raw_patch_but_unparsed" and (
        not pred_path.is_file() or not eval_status.has_log
    ):
        return "B"
    if eval_status.apply_failed:
        return "B"
    if eval_status.syntax_error:
        return "B"

    # No L3 eval → L2 pipeline failure (unparsed / no prediction submitted)
    if not eval_status.has_log:
        if loc.bucket == "no_patch":
            return "A"
        if loc.bucket == "applicable_patch" and not pred_path.is_file():
            return "B"
        task_dir, _ = latest_task_dir(repo_dir, instance_id)
        if patch_has_syntax_error(task_dir):
            return "B"
        return "B"

    if not eval_status.patch_applied:
        task_dir, _ = latest_task_dir(repo_dir, instance_id)
        if patch_has_syntax_error(task_dir):
            return "B"

    # A class — localization failure (before C when patch applied but wrong file)
    if loc.bucket == "no_patch":
        return "A"
    if loc.reason in (
        "no_bug_location_extracted",
        "wrong_fault_location",
        "no_task_dir",
    ):
        return "A"
    gold = set(loc.gold_files)
    loc_files = set(loc.loc_files)
    if gold and not (gold & loc_files):
        return "A"
    if not loc_files and not loc.has_bug_location:
        return "A"

    # C class — patch applied but tests failed with plausible localization
    if eval_status.patch_applied and eval_status.tests_failed:
        return "C"
    if eval_status.has_log and not eval_status.resolved:
        return "C"

    return "C"


def has_extracted_patch(task_dir: Path | None) -> bool:
    if task_dir is None:
        return False
    if (task_dir / "selected_patch.json").is_file():
        return True
    return bool(list(task_dir.glob("output_*/extracted_patch_*.diff")))


def classify_b_l2_failure(
    instance_id: str,
    eval_status: EvalStatus,
    loc: LocalizationInfo,
    repo_dir: Path,
    task_dir: Path | None,
) -> L2FailureInfo:
    pred_path = repo_dir / f"predictions_{instance_id}.json"

    if eval_status.has_log and eval_status.apply_failed:
        return L2FailureInfo(
            l2_category="L3 Apply Failed",
            l2_subtype="B3_l3_apply_failed",
            l2_reason=L2_SUBTYPE_META["B3_l3_apply_failed"]["summary"],
        )

    if loc.bucket == "raw_patch_but_unparsed" or loc.reason == "raw_patch_unparsed_no_eval":
        return L2FailureInfo(
            l2_category="L2 Unparsed",
            l2_subtype="B1_patch_unparsed",
            l2_reason=(
                "LLM 输出了 patch_raw，但补丁提取器无法生成有效 unified diff；"
                "产物落在 raw_patch_but_unparsed/，无 selected_patch / extracted_patch"
            ),
        )

    if loc.bucket == "applicable_patch" and not pred_path.is_file():
        if has_extracted_patch(task_dir):
            return L2FailureInfo(
                l2_category="L2 Unparsed",
                l2_subtype="B2_patch_not_submitted",
                l2_reason=(
                    "首轮 Agent 曾产出 extracted_patch，但 gap-fill 重跑 3 次仍为 L2 Unparsed；"
                    "未生成 predictions_sympy__*.json，未能进入 L3 隐藏测试"
                ),
            )
        return L2FailureInfo(
            l2_category="L2 Unparsed",
            l2_subtype="B2_patch_not_submitted",
            l2_reason=(
                "applicable_patch 目录存在，但 L2 门禁未通过；"
                "未生成 predictions_sympy__*.json，未能进入 L3 隐藏测试"
            ),
        )

    if not eval_status.has_log:
        return L2FailureInfo(
            l2_category="L2 Unparsed",
            l2_subtype="B2_patch_not_submitted",
            l2_reason="未进入 L3 评测（无 eval_log），补丁未成功交付给 SWE-bench",
        )

    return L2FailureInfo(
        l2_category="L2 Unparsed",
        l2_subtype="B2_patch_not_submitted",
        l2_reason="L2 流水线拦截，未进入 L3 评测",
    )


def pipeline_log_for_repo(repo_dir: Path) -> Path:
    rel = str(repo_dir).replace("\\", "/")
    if "ver1" in rel or "deepseek-lite-300-ver1" in rel:
        return ROOT / "lite300_logs" / "profiles" / "ver1" / "instance_pipeline.log"
    return ROOT / "lite300_logs" / "instance_pipeline.log"


def collect_paths(
    repo_dir: Path, instance_id: str, task_dir: Path | None, eval_status: EvalStatus
) -> dict[str, str | list[str] | None]:
    paths: dict[str, str | list[str] | None] = {}

    if task_dir is not None:
        issue = task_dir / "problem_statement.txt"
        meta = task_dir / "meta.json"
        paths["issue"] = rel_to_root(issue if issue.is_file() else meta)
        paths["trajectory_info_log"] = rel_to_root(task_dir / "info.log")
        paths["bug_locations"] = rel_to_root(
            next(iter(sorted(task_dir.glob("output_*/search/bug_locations_after_process.json"))), None)
        )
        paths["search_rounds"] = [
            rel_to_root(p) for p in sorted(task_dir.glob("output_*/search/search_round_*.json"))
        ] or None
        paths["agent_proxy"] = [
            rel_to_root(p) for p in sorted(task_dir.glob("output_*/search/agent_proxy_*.json"))
        ] or None
        paths["conv_patch"] = [
            rel_to_root(p) for p in sorted(task_dir.glob("output_*/conv_patch_*.json"))
        ] or None
        paths["conv_test"] = [
            rel_to_root(p) for p in sorted(task_dir.glob("output_*/conv_test_*.json"))
        ] or None
        paths["conv_reproducible"] = rel_to_root(
            next(iter(task_dir.glob("output_*/conv_reproducible.json")), None)
        )
        selected = task_dir / "selected_patch.json"
        paths["selected_patch"] = rel_to_root(selected if selected.is_file() else None)
        if selected.is_file():
            try:
                rel = json.loads(selected.read_text(encoding="utf-8")).get("selected_patch")
                if rel:
                    paths["extracted_patch"] = rel_to_root(task_dir / rel)
            except (json.JSONDecodeError, OSError):
                pass
        paths["patch_raw"] = [
            rel_to_root(p) for p in sorted(task_dir.glob("output_*/patch_raw_*.md"))
        ] or None
        paths["semantic_injection"] = [
            rel_to_root(p)
            for p in sorted(task_dir.glob("output_*/**/semantic_injection_ver1.json"))
        ] or None
        paths["acr_version"] = rel_to_root(
            next(iter(sorted(task_dir.glob("output_*/acr_version.json"))), None)
        )
        paths["developer_patch"] = rel_to_root(
            task_dir / "developer_patch.diff"
            if (task_dir / "developer_patch.diff").is_file()
            else task_dir / "meta.json"
        )

    task_one = repo_dir / f"tasks_one_{instance_id}.txt"
    if task_one.is_file():
        paths["tasks_one"] = rel_to_root(task_one)

    pred = repo_dir / f"predictions_{instance_id}.json"
    paths["prediction"] = rel_to_root(pred if pred.is_file() else None)
    paths["eval_log"] = eval_status.log_path
    paths["pipeline_log"] = rel_to_root(pipeline_log_for_repo(repo_dir))
    raw_unparsed = sorted(
        (repo_dir / "raw_patch_but_unparsed").glob(f"{instance_id}_*")
    )
    if raw_unparsed:
        paths["raw_patch_but_unparsed"] = rel_to_root(raw_unparsed[0])

    return paths


def analyze_repo(
    repo_dir: Path, task_list: Path | None = None
) -> list[InstanceRecord]:
    records: list[InstanceRecord] = []
    for instance_id in discover_instances(repo_dir, task_list):
        eval_status = read_eval_status(repo_dir, instance_id)
        task_dir, bucket = latest_task_dir(repo_dir, instance_id)
        loc = analyze_localization(repo_dir, instance_id, task_dir, bucket)

        l3_evaluated = eval_status.has_log
        pipeline_stage = "L3" if l3_evaluated else "L2_terminal"
        layer1 = "resolved" if eval_status.resolved else "unresolved"
        layer2 = None
        l2_failure = L2FailureInfo()
        if layer1 == "unresolved":
            layer2 = classify_layer2(instance_id, eval_status, loc, repo_dir)
            if layer2 == "B":
                l2_failure = classify_b_l2_failure(
                    instance_id, eval_status, loc, repo_dir, task_dir
                )

        paths = collect_paths(repo_dir, instance_id, task_dir, eval_status)
        records.append(
            InstanceRecord(
                instance_id=instance_id,
                layer1=layer1,
                layer2=layer2,
                l3_evaluated=l3_evaluated,
                pipeline_stage=pipeline_stage,
                l2_failure=l2_failure,
                eval_status=eval_status,
                localization=loc,
                paths=paths,
            )
        )
    return records


def pct(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{100.0 * count / total:.1f}%"


def is_ver1_repo(repo_dir: Path) -> bool:
    rel = str(repo_dir).replace("\\", "/")
    return "ver1" in rel or "deepseek-lite-300-ver1" in rel


def build_b_class_markdown(b_cases: list[InstanceRecord]) -> list[str]:
    lines = [
        "### B类 (L2 补丁交付失败，未进入 L3) instance_id 列表",
        "",
        ", ".join(r.instance_id for r in sorted(b_cases, key=lambda x: x.instance_id))
        or "_none_",
        "",
        "**说明**：B 类与 A/C 不同——不是 L3 隐藏测试失败，而是**补丁在交付给 SWE-bench 评测前被 L2 流水线拦截**，因此均无 `eval_logs`。",
        "",
    ]
    if not b_cases:
        return lines

    by_subtype: dict[str, list[InstanceRecord]] = {}
    for r in b_cases:
        subtype = r.l2_failure.l2_subtype or "unknown"
        by_subtype.setdefault(subtype, []).append(r)

    lines.extend(
        [
            "| 子类型 | 题数 | 含义 | 典型产物 |",
            "|--------|------|------|---------|",
        ]
    )
    for subtype in ("B1_patch_unparsed", "B2_patch_not_submitted", "B3_l3_apply_failed"):
        cases = by_subtype.get(subtype, [])
        if not cases:
            continue
        meta = L2_SUBTYPE_META.get(subtype, {"label": subtype, "summary": ""})
        artifact = {
            "B1_patch_unparsed": "`raw_patch_but_unparsed/`，无 `extracted_patch_*.diff`",
            "B2_patch_not_submitted": "`applicable_patch/` 有补丁，但无 `predictions_*.json`",
            "B3_l3_apply_failed": "`eval_logs` 含 `Apply patch failed`",
        }.get(subtype, "")
        lines.append(
            f"| {meta['label']} | {len(cases)} | {meta['summary']} | {artifact} |"
        )
    lines.extend(["", "#### B 类逐题说明", "", "| instance_id | 子类型 | L2 类别 | 说明 |", "|-------------|--------|---------|------|"])
    for r in sorted(b_cases, key=lambda x: x.instance_id):
        meta = L2_SUBTYPE_META.get(r.l2_failure.l2_subtype, {})
        label = meta.get("label", r.l2_failure.l2_subtype)
        lines.append(
            f"| {r.instance_id} | {label} | {r.l2_failure.l2_category} | {r.l2_failure.l2_reason} |"
        )
    lines.append("")
    return lines


def build_markdown(records: list[InstanceRecord], repo_dir: Path) -> str:
    total = len(records)
    resolved = [r for r in records if r.layer1 == "resolved"]
    unresolved = [r for r in records if r.layer1 == "unresolved"]
    a_cases = [r for r in unresolved if r.layer2 == "A"]
    b_cases = [r for r in unresolved if r.layer2 == "B"]
    c_cases = [r for r in unresolved if r.layer2 == "C"]
    fail_total = len(unresolved)
    ver1 = is_ver1_repo(repo_dir)
    title = "## SymPy Failure Analysis (Lite300 ver1)" if ver1 else "## SymPy Failure Analysis (Lite300)"
    pipeline_rel = rel_to_root(pipeline_log_for_repo(repo_dir))

    l3_count = sum(1 for r in records if r.l3_evaluated)
    l2_only = total - l3_count

    lines = [
        title,
        "",
        f"**Data source:** `{rel_to_root(repo_dir)}` (L3 authority: `eval_logs/`)",
    ]
    lines.append(
        f"**Machine-readable:** `{rel_to_root(repo_dir)}/sympy_failure_analysis.json` "
        "（含每题 `paths` / `records` / `eval_status.traceback`）"
    )
    lines.extend(
        [
        f"**Total instances:** {total}",
        f"**L3 evaluated:** {l3_count} | **L2 terminal (no L3):** {l2_only}",
        "",
        "### Layer 1: Resolved vs Unresolved",
        "",
        "| Layer | Category | Count | Percentage |",
        "|-------|----------|------:|-----------:|",
        f"| L1 | Resolved | {len(resolved)} | {pct(len(resolved), total)} |",
        f"| L1 | Unresolved | {len(unresolved)} | {pct(len(unresolved), total)} |",
        "",
        "### Layer 2: Failure Root Cause (Unresolved only)",
        "",
        "| Layer | Category | Count | % of Failures |",
        "|-------|----------|------:|--------------:|",
        f"| L2 | A - Localization Failure | {len(a_cases)} | {pct(len(a_cases), fail_total)} |",
        f"| L2 | B - L2 Pipeline Failure (no L3) | {len(b_cases)} | {pct(len(b_cases), fail_total)} |",
        f"| L2 | C - Logic/Assertion Failure | {len(c_cases)} | {pct(len(c_cases), fail_total)} |",
        "",
        ]
    )

    def id_list(cases: list[InstanceRecord]) -> str:
        return ", ".join(r.instance_id for r in sorted(cases, key=lambda x: x.instance_id))

    lines.extend(
        [
            "### A类 (Localization Failure) instance_id 列表",
            "",
            id_list(a_cases) or "_none_",
            "",
        ]
    )
    lines.extend(build_b_class_markdown(b_cases))
    lines.extend(
        [
            "### C类 (Logic/Assertion Failure) instance_id 列表",
            "",
            id_list(c_cases) or "_none_",
            "",
            "---",
            "",
            "## 排查路线图",
            "",
            "对每个 `{instance_id}`，在 JSON 输出 `paths` 字段中查看精确路径。通用模式（相对 `auto-code-rover/`）：",
            "",
            "| Artifact | Path pattern |",
            "|----------|--------------|",
            f"| Issue | `{rel_to_root(repo_dir)}/applicable_patch/{{instance_id}}_*/problem_statement.txt` |",
            f"| Agent log | `{rel_to_root(repo_dir)}/applicable_patch/{{instance_id}}_*/info.log` |",
            f"| Localization | `.../output_0/search/bug_locations_after_process.json` |",
            f"| Patch | `.../selected_patch.json` → `extracted_patch_*.diff` |",
            f"| Eval traceback | `{rel_to_root(repo_dir)}/eval_logs/{{instance_id}}.*.eval.log` |",
            f"| Pipeline | `{pipeline_rel}` |",
            "",
        ]
    )
    if ver1:
        lines.extend(
            [
                "| Semantic injection | `.../output_*/semantic_injection_ver1.json` (search + patch) |",
                "| ver1 branding | `.../output_*/acr_version.json` |",
                "| L2 unparsed | `{repo}/raw_patch_but_unparsed/{instance_id}_*/` |",
                "",
                "**Related:**",
                "",
                "- Baseline 同类分析: `lite300_output/repos/sympy/sympy_failure_analysis.md`",
                "- Baseline vs ver1 对比: `lite300_output_ver1/repos/sympy/report/baseline_vs_ver1_comparison.md`",
                "- L2 实验目录（与 sync 镜像）: `experiment/deepseek-lite-300-ver1/repos/sympy/`",
                "",
            ]
        )
    if not ver1:
        lines.extend(
            [
                "| L2 unparsed | `{repo}/raw_patch_but_unparsed/{instance_id}_*/` |",
                "",
            ]
        )
    lines.extend(
        [
            "| Class | Focus |",
            "|-------|-------|",
            "| **A** | `search/agent_proxy_*.json`, gold vs localized files |",
            "| **B** | `extract_status.json`, `raw_patch_but_unparsed/`, `selected_patch.json`, `predictions_*.json` 缺失, pipeline `L2 terminal fail` |",
            "| **C** | `conv_patch_*.json`, `extracted_patch_*.diff`, eval Traceback |",
        ]
    )
    if not ver1:
        lines.extend(
            [
                "",
                "### Baseline 单题错因分析建议",
                "",
                "1. 在 `sympy_failure_analysis.json` 的 `paths[instance_id]` 取精确路径。",
                "2. **C 类**：读 `eval_log` Traceback + `conv_patch_*.json` 中 patch 输出。",
                "3. **A 类**：对比 `localization.gold_files` vs `loc_files`（JSON `records` 字段）。",
                "4. **B 类**：查 `l2_subtype`（B1 补丁无法解析 / B2 未提交 prediction）及 pipeline log 中 `L2 Unparsed` / `L2 terminal fail`。",
                "",
            ]
        )
    if ver1:
        lines.extend(
            [
                "",
                "### ver1 单题错因分析建议",
                "",
                "1. 在 `sympy_failure_analysis.json` 的 `paths[instance_id]` 取精确路径。",
                "2. **C 类**：读 `eval_log` Traceback + `conv_patch_*.json` 中注入后的 prompt 与 patch 输出。",
                "3. **A 类**：对比 `localization.gold_files` vs `loc_files`（JSON `records` 字段）。",
                "4. **L2 未进 L3**（见下方附录）：查 `raw_patch_but_unparsed/` 与 pipeline log 中 `L2 Unparsed`。",
                "5. 语义注入是否生效：检查 `semantic_injection` 路径存在且 `rules_applied` 含三条规则。",
                "",
            ]
        )
        lines.extend(l2_not_l3_appendix(repo_dir))
    lines.append("")
    return "\n".join(lines)


def l2_not_l3_appendix(repo_dir: Path) -> list[str]:
    """List instances with L2 output but no L3 eval (ver1 pipeline gaps)."""
    report_path = repo_dir / "report" / "report.json"
    if not report_path.is_file():
        return []
    report = json.loads(report_path.read_text(encoding="utf-8"))
    generated = set(report.get("generated", []))
    with_logs = set(report.get("with_logs", []))
    missing_l3 = sorted(generated - with_logs)
    if not missing_l3:
        return []
    unparsed_set: set[str] = set()
    raw_dir = repo_dir / "raw_patch_but_unparsed"
    if raw_dir.is_dir():
        for d in raw_dir.iterdir():
            if d.is_dir():
                unparsed_set.add(instance_id_from_task_dir(d))
    lines = [
        "---",
        "",
        "## 附录：L2 有生成但未 L3 评测",
        "",
        f"共 **{len(missing_l3)}** 题（不在上文 `{len(generated) - len(missing_l3)}` 题 L3 分析集中）。",
        "",
        "### instance_id 列表",
        "",
        ", ".join(missing_l3),
        "",
        "### 常见原因",
        "",
        "- **L2 Unparsed**：patch 无法解析，落在 `raw_patch_but_unparsed/`（pipeline 终态上传飞书）",
        "- **L2 未跑完 / 无 applicable patch**：无 prediction，未进入 L3",
        "",
    ]
    l2_unparsed = [i for i in missing_l3 if i in unparsed_set]
    if l2_unparsed:
        lines.extend(
            [
                "### 其中 raw_patch_but_unparsed（L2 Unparsed 候选）",
                "",
                ", ".join(l2_unparsed),
                "",
            ]
        )
    return lines


def build_json_output(records: list[InstanceRecord], repo_dir: Path | None = None) -> dict:
    resolved = sorted(r.instance_id for r in records if r.layer1 == "resolved")
    a_list = []
    b_list = []
    c_list = []
    paths_map = {}

    for r in records:
        paths_map[r.instance_id] = r.paths
        if r.layer2 == "A":
            a_list.append(
                {
                    "instance_id": r.instance_id,
                    "reason": r.localization.reason,
                    "gold_files": r.localization.gold_files,
                    "loc_files": r.localization.loc_files,
                    "bucket": r.localization.bucket,
                }
            )
        elif r.layer2 == "B":
            b_list.append(
                {
                    "instance_id": r.instance_id,
                    "l2_category": r.l2_failure.l2_category,
                    "l2_subtype": r.l2_failure.l2_subtype,
                    "l2_reason": r.l2_failure.l2_reason,
                    "bucket": r.localization.bucket,
                    "pipeline_stage": r.pipeline_stage,
                    "apply_failed": r.eval_status.apply_failed,
                }
            )
        elif r.layer2 == "C":
            c_list.append(r.instance_id)

    l3_evaluated = sum(1 for r in records if r.l3_evaluated)
    b1_count = sum(1 for x in b_list if x.get("l2_subtype") == "B1_patch_unparsed")
    b2_count = sum(1 for x in b_list if x.get("l2_subtype") == "B2_patch_not_submitted")
    b3_count = sum(1 for x in b_list if x.get("l2_subtype") == "B3_l3_apply_failed")
    payload: dict = {
        "summary": {
            "total": len(records),
            "l3_evaluated": l3_evaluated,
            "l2_only": len(records) - l3_evaluated,
            "resolved": len(resolved),
            "unresolved": len(records) - len(resolved),
            "A_localization": len(a_list),
            "B_l2_pipeline": len(b_list),
            "B1_patch_unparsed": b1_count,
            "B2_patch_not_submitted": b2_count,
            "B3_l3_apply_failed": b3_count,
            "C_logic_assertion": len(c_list),
        },
        "resolved": resolved,
        "unresolved": {
            "A_localization": sorted(a_list, key=lambda x: x["instance_id"]),
            "B_l2_pipeline": sorted(b_list, key=lambda x: x["instance_id"]),
            "C_logic_assertion": sorted(c_list),
        },
        "records": [
            {
                "instance_id": r.instance_id,
                "layer1": r.layer1,
                "layer2": r.layer2,
                "l3_evaluated": r.l3_evaluated,
                "pipeline_stage": r.pipeline_stage,
                "l2_failure": asdict(r.l2_failure) if r.layer2 == "B" else None,
                "eval_status": asdict(r.eval_status),
                "localization": asdict(r.localization),
            }
            for r in records
        ],
        "paths": paths_map,
    }
    if repo_dir is not None and is_ver1_repo(repo_dir):
        payload["version"] = "ver1"
        payload["semantic_injection"] = True
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze SymPy SWE-bench failure categories.")
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=ROOT / "lite300_output" / "repos" / "sympy",
        help="SymPy repo experiment directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "lite300_output" / "repos" / "sympy" / "sympy_failure_analysis.json",
        help="JSON output path",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=ROOT / "lite300_output" / "repos" / "sympy" / "sympy_failure_analysis.md",
        help="Markdown report path",
    )
    parser.add_argument(
        "--task-list",
        type=Path,
        default=ROOT / "conf" / "lite300_tasks" / "sympy.txt",
        help="Full instance list (one id per line); fallback to L3 artifacts if missing",
    )
    args = parser.parse_args()
    repo_dir = args.repo_dir.resolve()
    task_list = args.task_list.resolve() if args.task_list else None

    if not repo_dir.is_dir():
        print(f"ERROR: repo dir not found: {repo_dir}", file=sys.stderr)
        return 1

    records = analyze_repo(repo_dir, task_list)
    md = build_markdown(records, repo_dir)
    payload = build_json_output(records, repo_dir)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    args.markdown.write_text(md, encoding="utf-8")

    print(md)
    print()
    print(f"JSON written to: {args.output}")
    print(f"Markdown written to: {args.markdown}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
