#!/usr/bin/env python3
"""Run SWE-bench docker eval one instance at a time (L3 incremental)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST_ACR_ROOT = Path(os.environ.get("HOST_ACR_ROOT", "/datadisk/pengxm/auto-code-rover"))
DOCKER_DIR = Path("/opt/SWE-bench-docker")
SWE_BENCH_DIR = Path("/opt/SWE-bench")


@dataclass
class EvalPaths:
    expr_dir: Path
    predictions: Path
    sanitized_predictions: Path
    progress_file: Path
    eval_state_file: Path
    eval_log_dir: Path
    report_dir: Path


def resolve_paths(expr_dir: Path) -> EvalPaths:
    expr_dir = expr_dir.resolve()
    return EvalPaths(
        expr_dir=expr_dir,
        predictions=expr_dir / "predictions_for_swebench.json",
        sanitized_predictions=expr_dir / "predictions_for_swebench.sanitized.json",
        progress_file=expr_dir / "eval_progress.json",
        eval_state_file=expr_dir / "eval_state.json",
        eval_log_dir=expr_dir / "eval_logs",
        report_dir=expr_dir / "report",
    )


def sanitize_prediction(pred: dict) -> dict:
    """SWE-bench-docker log paths break when model_name_or_path contains '/'."""
    out = dict(pred)
    model = out.get("model_name_or_path")
    if isinstance(model, str):
        out["model_name_or_path"] = model.replace("/", "-")
    return out


def load_predictions(paths: EvalPaths) -> dict[str, dict]:
    data = json.loads(paths.predictions.read_text())
    if isinstance(data, list):
        items = {item["instance_id"]: sanitize_prediction(item) for item in data}
    else:
        items = {k: sanitize_prediction(v) for k, v in data.items()}
    return items


def write_sanitized_predictions(preds: dict[str, dict], paths: EvalPaths) -> Path:
    items = [preds[k] for k in sorted(preds)]
    paths.sanitized_predictions.write_text(json.dumps(items, indent=2))
    return paths.sanitized_predictions


def load_progress(paths: EvalPaths) -> set[str]:
    if paths.progress_file.exists():
        return set(json.loads(paths.progress_file.read_text()).get("done", []))
    return set()


def save_progress(done: set[str], paths: EvalPaths) -> None:
    paths.progress_file.write_text(json.dumps({"done": sorted(done)}, indent=2))


def load_eval_state(paths: EvalPaths) -> dict:
    if paths.eval_state_file.is_file():
        data = json.loads(paths.eval_state_file.read_text(encoding="utf-8"))
        if isinstance(data.get("instances"), dict):
            return data
    return {"instances": {}}


def save_eval_state(state: dict, paths: EvalPaths) -> None:
    paths.eval_state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def record_eval_timing(
    state: dict,
    instance_id: str,
    *,
    elapsed_s: float,
    status: str,
    note: str = "",
) -> None:
    state.setdefault("instances", {})[instance_id] = {
        "elapsed_s": round(elapsed_s, 1),
        "status": status,
        "note": note,
    }


def run_one(
    instance_id: str,
    predictions_path: Path,
    log_dir: Path,
    *,
    num_processes: int = 1,
) -> None:
    tasks_json = SWE_BENCH_DIR / "data" / "swe-bench.json"
    cmd = [
        "python",
        str(DOCKER_DIR / "run_evaluation.py"),
        "--predictions_path",
        str(predictions_path),
        "--log_dir",
        str(log_dir),
        "--swe_bench_tasks",
        str(tasks_json),
        "--namespace",
        "autocoderover",
        "--timeout",
        "3600",
        "--num_processes",
        str(num_processes),
    ]
    env = os.environ.copy()
    env.setdefault("HOST_ACR_ROOT", str(HOST_ACR_ROOT))
    subprocess.run(cmd, cwd=DOCKER_DIR, check=True, env=env)


def eval_log_path(instance_id: str, pred_item: dict, log_dir: Path) -> Path:
    model = pred_item["model_name_or_path"]
    return log_dir / f"{instance_id}.{model}.eval.log"


def eval_log_exists(instance_id: str, pred_item: dict, log_dir: Path) -> bool:
    path = eval_log_path(instance_id, pred_item, log_dir)
    return path.is_file() and path.stat().st_size > 0


def prune_eval_images(*, prune_preloaded: bool = False) -> None:
    env = os.environ.copy()
    env["PRUNE_AUTOCODEROVER_IMAGES"] = "1" if prune_preloaded else "0"
    subprocess.run(
        ["bash", str(ROOT / "scripts/prune_eval_images.sh")],
        check=False,
        env=env,
    )


def generate_report(preds: dict[str, dict], paths: EvalPaths) -> None:
    paths.report_dir.mkdir(parents=True, exist_ok=True)
    sanitized_preds_path = write_sanitized_predictions(preds, paths)
    cmd = [
        "python",
        str(DOCKER_DIR / "generate_report.py"),
        "--predictions_path",
        str(sanitized_preds_path),
        "--log_dir",
        str(paths.eval_log_dir),
        "--swe_bench_tasks",
        str(SWE_BENCH_DIR / "data" / "swe-bench.json"),
        "--output_dir",
        str(paths.report_dir),
    ]
    subprocess.run(cmd, cwd=DOCKER_DIR, check=True)
    print(f"Report: {paths.report_dir / 'report.json'} (predictions: {sanitized_preds_path.name})")


def run_eval_loop(
    preds: dict[str, dict],
    paths: EvalPaths,
    *,
    resume: bool,
    prune_preloaded: bool,
    only_ids: set[str] | None = None,
    num_processes: int = 1,
) -> None:
    done = load_progress(paths) if resume else set()
    eval_state = load_eval_state(paths)
    paths.eval_log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(paths.eval_log_dir, 0o777)

    for instance_id in preds:
        if only_ids is not None and instance_id not in only_ids:
            continue
        if instance_id in done:
            existing = eval_state.get("instances", {}).get(instance_id, {})
            if existing.get("elapsed_s"):
                print(f"Skip (done): {instance_id}")
                continue
            print(
                f"Re-eval (done, missing elapsed_s): {instance_id}",
                file=sys.stderr,
            )

        print(f"=== Eval: {instance_id} @ {datetime.now().isoformat()} ===")
        single_pred = paths.expr_dir / f"predictions_{instance_id}.json"
        pred_item = preds[instance_id]
        single_pred.write_text(json.dumps([pred_item], indent=2))
        t0 = time.perf_counter()
        try:
            run_one(instance_id, single_pred, paths.eval_log_dir, num_processes=num_processes)
            elapsed_s = time.perf_counter() - t0
            if eval_log_exists(instance_id, pred_item, paths.eval_log_dir):
                done.add(instance_id)
                save_progress(done, paths)
                record_eval_timing(
                    eval_state,
                    instance_id,
                    elapsed_s=elapsed_s,
                    status="done",
                )
            else:
                print(f"WARNING: no eval log for {instance_id}; not marking done", file=sys.stderr)
                record_eval_timing(
                    eval_state,
                    instance_id,
                    elapsed_s=elapsed_s,
                    status="failed",
                    note="no eval log produced",
                )
        except subprocess.CalledProcessError as exc:
            elapsed_s = time.perf_counter() - t0
            record_eval_timing(
                eval_state,
                instance_id,
                elapsed_s=elapsed_s,
                status="failed",
                note=f"run_evaluation exit {exc.returncode}",
            )
            raise
        finally:
            save_eval_state(eval_state, paths)
            prune_eval_images(prune_preloaded=prune_preloaded)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expr-dir",
        type=Path,
        default=ROOT / "experiment" / "deepseek-lite-pilot",
        help="Experiment output directory (default: experiment/deepseek-lite-pilot)",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Skip Docker eval; regenerate sanitized predictions and report only",
    )
    parser.add_argument(
        "--prune-preloaded-images",
        action="store_true",
        help="After each instance, also remove autocoderover/* images (legacy; "
        "default keeps preloaded testbeds on disk).",
    )
    parser.add_argument(
        "--instance-id",
        action="append",
        default=[],
        metavar="ID",
        help="Eval only this instance (repeatable)",
    )
    parser.add_argument(
        "--instances-file",
        type=Path,
        default=None,
        help="File with one instance_id per line to eval",
    )
    parser.add_argument(
        "--num-processes",
        type=int,
        default=1,
        help="Docker eval worker parallelism (ver1: use 1-2 on local hardware)",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.expr_dir)

    if not paths.predictions.exists():
        print(f"Missing {paths.predictions}; run agent first (L2).", file=sys.stderr)
        return 1
    if not (DOCKER_DIR / "run_evaluation.py").exists():
        print("SWE-bench-docker not installed. Run setup_swe_bench_docker.sh", file=sys.stderr)
        return 1

    preds = load_predictions(paths)

    only_ids: set[str] | None = None
    if args.instances_file:
        lines = [
            ln.strip()
            for ln in args.instances_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        only_ids = set(lines)
    if args.instance_id:
        only_ids = (only_ids or set()) | set(args.instance_id)
    if only_ids:
        missing = sorted(only_ids - set(preds))
        if missing:
            print(f"WARNING: no prediction for: {', '.join(missing)}", file=sys.stderr)

    if args.report_only:
        print("[report-only] Skipping per-instance Docker eval.")
        generate_report(preds, paths)
        return 0

    run_eval_loop(
        preds,
        paths,
        resume=args.resume,
        prune_preloaded=args.prune_preloaded_images,
        only_ids=only_ids,
        num_processes=max(1, min(args.num_processes, 2)),
    )
    generate_report(preds, paths)
    return 0


if __name__ == "__main__":
    sys.exit(main())
