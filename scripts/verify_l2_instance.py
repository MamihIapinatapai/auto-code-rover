#!/usr/bin/env python3
"""Per-instance L2 verification (PASS/FAIL + failure category)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from lite300_instance_utils import (  # noqa: E402
    expr_dir_for_instance,
    find_task_dir,
    repo_from_instance_id,
    resolve_pipeline_profile,
)

L2_MISSING = "L2 Missing"
L2_NO_PATCH = "L2 No Patch"
L2_UNPARSED = "L2 Unparsed"


@dataclass
class L2VerifyResult:
    instance_id: str
    passed: bool
    category: str
    message: str = ""


def verify_l2_instance(instance_id: str, expr_dir: Path) -> L2VerifyResult:
    predictions_path = expr_dir / "predictions_for_swebench.json"
    pred_ids: set[str] = set()
    if predictions_path.is_file():
        predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
        if isinstance(predictions, list):
            pred_ids = {str(p["instance_id"]) for p in predictions}
        else:
            pred_ids = {str(k) for k in predictions.keys()}

    if find_task_dir(expr_dir, instance_id, "no_patch"):
        return L2VerifyResult(instance_id, False, L2_NO_PATCH, "in no_patch/")

    if find_task_dir(expr_dir, instance_id, "raw_patch_but_unparsed"):
        return L2VerifyResult(instance_id, False, L2_UNPARSED, "in raw_patch_but_unparsed/")

    if instance_id not in pred_ids:
        return L2VerifyResult(instance_id, False, L2_MISSING, "not in predictions")

    task_dir = find_task_dir(expr_dir, instance_id, "applicable_patch")
    if task_dir is None:
        return L2VerifyResult(
            instance_id,
            False,
            L2_MISSING,
            "in predictions but no applicable_patch dir",
        )

    if not (task_dir / "cost.json").is_file():
        return L2VerifyResult(instance_id, False, L2_UNPARSED, "missing cost.json")

    info_log = task_dir / "info.log"
    if not info_log.is_file():
        return L2VerifyResult(instance_id, False, L2_UNPARSED, "missing info.log")

    if f"Task {instance_id} completed successfully" not in info_log.read_text(
        encoding="utf-8", errors="replace"
    ):
        return L2VerifyResult(instance_id, False, L2_UNPARSED, "patch selection incomplete")

    return L2VerifyResult(instance_id, True, "None", "ok")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify L2 output for one instance.")
    parser.add_argument("--instance-id", required=True)
    parser.add_argument(
        "--expr-dir",
        type=Path,
        default=None,
        help="Override experiment dir (default: derived from instance id)",
    )
    parser.add_argument(
        "--pipeline-profile",
        default=None,
        help="Pipeline profile (baseline, ver1). Default: PIPELINE_PROFILE env",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON result on stdout",
    )
    args = parser.parse_args()

    instance_id = args.instance_id
    if repo_from_instance_id(instance_id) is None:
        print(f"Unknown repo for instance: {instance_id}", file=sys.stderr)
        return 2

    profile = resolve_pipeline_profile(args.pipeline_profile)

    expr_dir = args.expr_dir
    if expr_dir is None:
        expr_dir = expr_dir_for_instance(ROOT, instance_id, profile)
    if expr_dir is None or not expr_dir.is_dir():
        print(
            f"Missing expr dir for {instance_id} (profile={profile.name}, "
            f"expected under {profile.experiment_prefix}/)",
            file=sys.stderr,
        )
        return 2

    result = verify_l2_instance(instance_id, expr_dir.resolve())
    if args.json:
        print(
            json.dumps(
                {
                    "instance_id": result.instance_id,
                    "passed": result.passed,
                    "category": result.category,
                    "message": result.message,
                },
                ensure_ascii=False,
            )
        )
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {instance_id} category={result.category} {result.message}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
