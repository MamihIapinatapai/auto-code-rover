#!/usr/bin/env python3
"""Run specification parser (issue parsing agent) on DeepSWE Python tasks only."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.deepswe.adapter import load_task  # noqa: E402
from app.infrastructure.shared_memory import SharedMemoryStore  # noqa: E402
from app.model.gpt import common  # noqa: E402
from app.model.register import register_all_models  # noqa: E402
from app.raw_tasks import RawDeepSweTask  # noqa: E402
from app.spec_parser.agent import SpecParsingAgent  # noqa: E402
from app.spec_parser.pipeline import (  # noqa: E402
    V2_PARSER_VERSION,
    V3_PARSER_VERSION,
    apply_spec_parser_version,
    configure_repo_enrichment,
)


def resolve_project_path(path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def load_dotenv() -> None:
    env_path = ROOT / "conf" / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_conf(conf_file: Path) -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    with conf_file.open(encoding="utf-8") as f:
        parser.read_string("[DEFAULT]\n" + f.read())
    return parser["DEFAULT"]


def parse_task_list(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def _resolve_repro_script(out_dir: Path) -> Path | None:
    """Locate generated acceptance script (BUG_FIX or FEATURE filename)."""
    swm_path = out_dir / SharedMemoryStore.FILENAME
    if swm_path.is_file():
        try:
            swm = json.loads(swm_path.read_text(encoding="utf-8"))
            fname = (
                (swm.get("structured_spec") or {})
                .get("repro_script", {})
                .get("filename")
            )
            if fname:
                candidate = out_dir / fname
                if candidate.is_file():
                    return candidate
        except (json.JSONDecodeError, OSError, AttributeError, TypeError):
            pass
    for name in ("reproduce_issue.py", "test_feature.py"):
        candidate = out_dir / name
        if candidate.is_file():
            return candidate
    return None


def _artifact_flags(out_dir: Path) -> dict:
    ee_path = out_dir / SharedMemoryStore.EXECUTION_EVIDENCE_FILENAME
    calibration_passed = None
    overall_exit_code = None
    if ee_path.is_file():
        try:
            ee = json.loads(ee_path.read_text(encoding="utf-8"))
            calibration_passed = ee.get("calibration_passed")
            overall_exit_code = ee.get("overall_exit_code")
        except (json.JSONDecodeError, OSError):
            pass
    repro = _resolve_repro_script(out_dir)
    return {
        "reproduce_issue_exists": repro is not None,
        "reproduce_script_path": str(repro) if repro else None,
        "problem_statement_exists": (out_dir / "problem_statement.txt").is_file(),
        "repair_draft_exists": (out_dir / "repair_draft.json").is_file(),
        "repo_enrichment_exists": (
            out_dir / SharedMemoryStore.REPO_ENRICHMENT_FILENAME
        ).is_file(),
        "calibration_passed": calibration_passed,
        "overall_exit_code": overall_exit_code,
    }


def run_one_task(
    task_id: str,
    tasks_dir: Path,
    repos_dir: Path,
    output_root: Path,
    stop_after: str,
) -> dict:
    task_path = tasks_dir / task_id
    out_dir = output_root / task_id
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    result: dict = {
        "task_id": task_id,
        "output_dir": str(out_dir),
        "ok": False,
        "parser_version": getattr(config, "spec_parser_version", V2_PARSER_VERSION),
        "repo_enrichment_enabled": bool(config.spec_parser_enable_repo_enrichment),
        "use_v3_prompts": bool(getattr(config, "spec_parser_use_v3_prompts", False)),
        "script_review": bool(getattr(config, "spec_parser_enable_script_review", False)),
    }

    try:
        raw = RawDeepSweTask.from_task_dir(str(task_path), str(repos_dir))
        raw.apply_runtime_config()
        record = load_task(task_path)
        (out_dir / "problem_statement.txt").write_text(
            record.problem_statement, encoding="utf-8"
        )

        agent = SpecParsingAgent(raw.to_task(), str(out_dir))
        spec = agent.run(
            record.problem_statement,
            stop_after=stop_after,  # type: ignore[arg-type]
            use_llm_for_script=False if stop_after == "enrich" else True,
        )

        search_ctx = out_dir / SharedMemoryStore.SEARCH_CONTEXT_FILENAME
        swm_path = out_dir / SharedMemoryStore.FILENAME
        flags = _artifact_flags(out_dir)
        result.update(
            {
                "ok": True,
                "elapsed_s": round(time.time() - started, 1),
                "search_context": str(search_ctx),
                "search_context_bytes": search_ctx.stat().st_size if search_ctx.is_file() else 0,
                "shared_working_memory": str(swm_path),
                "repair_goals_count": len(spec.repair_goals),
                "stop_after": stop_after,
                "parser_version": spec.parser_version,
                **flags,
            }
        )
    except Exception as exc:
        flags = _artifact_flags(out_dir)
        result.update(
            {
                "ok": False,
                "elapsed_s": round(time.time() - started, 1),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                **flags,
            }
        )
        (out_dir / "error.txt").write_text(result["traceback"], encoding="utf-8")

    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run spec parser on DeepSWE Python tasks (issue parsing agent only)"
    )
    parser.add_argument(
        "--conf-file",
        default=str(ROOT / "conf/deepseek-deepswe-spec-parser.conf"),
    )
    parser.add_argument(
        "--max-tasks",
        type=int,
        default=int(os.environ.get("DEEPSWE_MAX_TASKS", "0") or "0"),
        help="Run only first N tasks (0 = all).",
    )
    parser.add_argument(
        "--stop-after",
        choices=["extract", "enrich", "fusion", "calibration", "full"],
        default=None,
        help="Override spec_parser_stop_after from conf.",
    )
    parser.add_argument(
        "--spec-parser-version",
        choices=["2.2.0", "3.0.0", "3.1.0", "3.2.0", "3.3.0", "3.3.1", "3.4.0"],
        default=None,
        help="Pipeline version: 3.x disables P2; 3.3 chains; 3.3.1 ScriptAnchor; 3.4.0 Contract-First.",
    )
    parser.add_argument(
        "--use-v3-prompts",
        action="store_true",
        default=False,
        help="Use v3.0 dual script prompts (BUG_FIX/FEATURE) and scaffold wrapping.",
    )
    parser.add_argument(
        "--enable-script-review",
        action="store_true",
        default=False,
        help="Enable v3.2 script reviewer LLM on lint/gate failure.",
    )
    parser.add_argument(
        "--no-script-review",
        action="store_true",
        default=False,
        help="Disable v3.2 script reviewer (use rule-only feedback like 3.1).",
    )
    parser.add_argument(
        "--no-evidence-chain",
        action="store_true",
        default=False,
        help="Disable v3.3 Issue↔AC evidence chain.",
    )
    parser.add_argument(
        "--no-decision-trace",
        action="store_true",
        default=False,
        help="Disable v3.3 decision-trace persistence.",
    )
    parser.add_argument(
        "--no-draft-best-of",
        action="store_true",
        default=False,
        help="Disable v3.3 draft best-of selection.",
    )
    parser.add_argument(
        "--no-script-anchor",
        action="store_true",
        default=False,
        help="Disable v3.3.1 ScriptAnchor.",
    )
    parser.add_argument(
        "--no-script-anchor-tier2",
        action="store_true",
        default=False,
        help="Disable v3.3.1 ScriptAnchor Tier2 inspect.",
    )
    parser.add_argument(
        "--enable-contract-llm-review",
        action="store_true",
        default=False,
        help="Enable v3.4 BehaviorContract LLM semantic review (after BC pass).",
    )
    parser.add_argument(
        "--enable-script-contract-llm",
        action="store_true",
        default=False,
        help="Enable v3.4 SCC-L script↔contract LLM review (after SCC-M).",
    )
    parser.add_argument(
        "--contract-llm-review-mode",
        choices=["off", "always", "high_risk_only"],
        default=None,
        help="Mode for contract LLM review (default high_risk_only when enabled).",
    )
    parser.add_argument(
        "--script-contract-llm-mode",
        choices=["off", "always", "high_risk_only"],
        default=None,
        help="Mode for SCC-L (default high_risk_only when enabled).",
    )
    parser.add_argument(
        "--no-repo-enrichment",
        action="store_true",
        help="Disable P2 repo_enrichment (static AST analysis).",
    )
    parser.add_argument(
        "--with-repo-enrichment",
        action="store_true",
        help="Force-enable P2 repo_enrichment (ablation vs v3 no-static).",
    )
    args = parser.parse_args()

    load_dotenv()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY not set (conf/.env)", file=sys.stderr)
        return 1

    conf_path = Path(args.conf_file).resolve()
    cfg = read_conf(conf_path)

    tasks_dir = resolve_project_path(cfg["deepswe_tasks_dir"])
    repos_dir = resolve_project_path(cfg["deepswe_repos_dir"])
    output_root = resolve_project_path(cfg["output_dir"]) / cfg["id"]
    task_list_path = resolve_project_path(cfg["selected_tasks_file"])

    stop_after = args.stop_after or cfg.get("spec_parser_stop_after", "enrich")
    model = cfg.get("model", "litellm-generic-deepseek/deepseek-chat").split()
    temperature = float(cfg.get("temperature", "0.2"))

    if os.environ.get("ACR_SPEC_PARSER_VERSION", "").strip():
        apply_spec_parser_version(os.environ["ACR_SPEC_PARSER_VERSION"].strip())
    if args.spec_parser_version:
        apply_spec_parser_version(args.spec_parser_version)
    if os.environ.get("ACR_SPEC_PARSER_USE_V3_PROMPTS", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        config.spec_parser_use_v3_prompts = True
    if args.use_v3_prompts:
        config.spec_parser_use_v3_prompts = True
    if args.enable_script_review:
        config.spec_parser_enable_script_review = True
    if args.no_script_review:
        config.spec_parser_enable_script_review = False
    if getattr(args, "no_evidence_chain", False):
        config.spec_parser_enable_evidence_chain = False
    if getattr(args, "no_decision_trace", False):
        config.spec_parser_enable_decision_trace = False
    if getattr(args, "no_draft_best_of", False):
        config.spec_parser_enable_draft_best_of = False
    if getattr(args, "no_script_anchor", False):
        config.spec_parser_enable_script_anchor = False
        config.spec_parser_enable_script_anchor_tier2 = False
    if getattr(args, "no_script_anchor_tier2", False):
        config.spec_parser_enable_script_anchor_tier2 = False
    # v3.4 semantic LLM reviews — must apply AFTER apply_spec_parser_version
    if getattr(args, "enable_contract_llm_review", False):
        config.spec_parser_enable_contract_llm_review = True
        config.spec_parser_contract_llm_review_mode = (
            args.contract_llm_review_mode or "high_risk_only"
        )
    elif getattr(args, "contract_llm_review_mode", None):
        config.spec_parser_contract_llm_review_mode = args.contract_llm_review_mode
        if args.contract_llm_review_mode != "off":
            config.spec_parser_enable_contract_llm_review = True
    if getattr(args, "enable_script_contract_llm", False):
        config.spec_parser_enable_script_contract_llm = True
        config.spec_parser_script_contract_llm_mode = (
            args.script_contract_llm_mode or "high_risk_only"
        )
    elif getattr(args, "script_contract_llm_mode", None):
        config.spec_parser_script_contract_llm_mode = args.script_contract_llm_mode
        if args.script_contract_llm_mode != "off":
            config.spec_parser_enable_script_contract_llm = True

    config.enable_spec_parser = True
    config.enable_sympy_pipeline_v2 = False
    configure_repo_enrichment(
        stop_after=stop_after,
        no_repo_enrichment=args.no_repo_enrichment,
        with_repo_enrichment=args.with_repo_enrichment,
    )

    register_all_models()
    common.set_model(model[0] if model else "litellm-generic-deepseek/deepseek-chat")
    common.MODEL_TEMP = temperature

    task_ids = parse_task_list(task_list_path)
    if args.max_tasks and args.max_tasks > 0:
        task_ids = task_ids[: args.max_tasks]

    output_root.mkdir(parents=True, exist_ok=True)
    repos_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"DeepSWE spec parser: {len(task_ids)} task(s), stop_after={stop_after}, "
        f"parser_version={config.spec_parser_version}, "
        f"v3_prompts={config.spec_parser_use_v3_prompts}, "
        f"script_review={config.spec_parser_enable_script_review}, "
        f"contract_llm_review={config.spec_parser_enable_contract_llm_review}"
        f"/{getattr(config, 'spec_parser_contract_llm_review_mode', '')}, "
        f"scc_l={config.spec_parser_enable_script_contract_llm}"
        f"/{getattr(config, 'spec_parser_script_contract_llm_mode', '')}, "
        f"repo_enrichment={config.spec_parser_enable_repo_enrichment}"
    )
    print(f"Output: {output_root}")

    report = {
        "expr_id": cfg["id"],
        "output_root": str(output_root),
        "stop_after": stop_after,
        "parser_version": config.spec_parser_version,
        "use_v3_prompts": bool(config.spec_parser_use_v3_prompts),
        "script_review": bool(config.spec_parser_enable_script_review),
        "contract_llm_review": bool(
            getattr(config, "spec_parser_enable_contract_llm_review", False)
        ),
        "contract_llm_review_mode": getattr(
            config, "spec_parser_contract_llm_review_mode", "off"
        ),
        "script_contract_llm": bool(
            getattr(config, "spec_parser_enable_script_contract_llm", False)
        ),
        "script_contract_llm_mode": getattr(
            config, "spec_parser_script_contract_llm_mode", "off"
        ),
        "repo_enrichment_enabled": bool(config.spec_parser_enable_repo_enrichment),
        "model": model[0] if model else "",
        "started_at": datetime.now().isoformat(),
        "tasks": [],
    }

    ok_count = 0
    calib_pass = 0
    calib_fail = 0
    calib_unknown = 0
    reproduce_count = 0
    for idx, task_id in enumerate(task_ids, 1):
        print(f"\n[{idx}/{len(task_ids)}] {task_id}")
        task_result = run_one_task(
            task_id, tasks_dir, repos_dir, output_root, stop_after
        )
        report["tasks"].append(task_result)
        if task_result.get("reproduce_issue_exists"):
            reproduce_count += 1
        cp = task_result.get("calibration_passed")
        if cp is True:
            calib_pass += 1
        elif cp is False:
            calib_fail += 1
        else:
            calib_unknown += 1
        if task_result.get("ok"):
            ok_count += 1
            print(
                f"  OK search_context={task_result.get('search_context_bytes')} bytes "
                f"reproduce={task_result.get('reproduce_issue_exists')} "
                f"calib={task_result.get('calibration_passed')} "
                f"({task_result.get('elapsed_s')}s)"
            )
        else:
            print(f"  FAIL: {task_result.get('error')}")

    report["finished_at"] = datetime.now().isoformat()
    report["summary"] = {
        "total": len(task_ids),
        "ok": ok_count,
        "failed": len(task_ids) - ok_count,
        "reproduce_issue_count": reproduce_count,
        "calibration_passed": calib_pass,
        "calibration_failed": calib_fail,
        "calibration_unknown": calib_unknown,
    }

    report_path = output_root / "spec_parser_run_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote report: {report_path}")
    print(f"Summary: {ok_count}/{len(task_ids)} succeeded")
    print(
        f"reproduce_issue.py: {reproduce_count}/{len(task_ids)}; "
        f"calibration passed/failed/unknown: "
        f"{calib_pass}/{calib_fail}/{calib_unknown}"
    )
    return 0 if ok_count == len(task_ids) else 1


if __name__ == "__main__":
    raise SystemExit(main())
