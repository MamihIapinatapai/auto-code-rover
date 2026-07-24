"""DeepSWE batch runner utilities."""

from __future__ import annotations

import json
import shutil
from glob import glob
from os.path import join as pjoin
from pathlib import Path

from app.post_process import get_final_patch_path


def collect_patches_from_run(
    experiment_dir: str,
    patches_dir: str,
    *,
    model_name: str,
    predictions_name: str = "deepswe_predictions.json",
) -> dict:
    """Copy extracted patches from an experiment run into patches_dir."""
    expr = Path(experiment_dir).resolve()
    out = Path(patches_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    predictions: list[dict] = []
    stats = {"with_patch": 0, "no_patch": 0, "instances": {}}

    for task_dir in sorted(expr.iterdir()):
        if not task_dir.is_dir():
            continue
        meta_path = task_dir / "meta.json"
        if not meta_path.is_file():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        instance_id = meta.get("task_id") or meta.get("task_info", {}).get("instance_id")
        if not instance_id:
            continue

        patch_path = get_final_patch_path(str(task_dir))
        dest = out / f"{instance_id}.patch"
        patch_content = ""

        if patch_path and Path(patch_path).is_file():
            patch_content = Path(patch_path).read_text(encoding="utf-8", errors="replace")
            shutil.copy2(patch_path, dest)
            stats["with_patch"] += 1
            stats["instances"][instance_id] = "APPLICABLE_PATCH"
        else:
            dest.write_text("", encoding="utf-8")
            stats["no_patch"] += 1
            stats["instances"][instance_id] = "NO_PATCH"

        predictions.append(
            {
                "instance_id": instance_id,
                "model_patch": patch_content,
                "model_name_or_path": model_name.replace("/", "-"),
            }
        )

    pred_file = expr.parent / predictions_name
    if predictions_name.startswith("/") or "/" in predictions_name:
        pred_file = Path(predictions_name)
    else:
        pred_file = expr / predictions_name

    pred_file.write_text(json.dumps(predictions, indent=2), encoding="utf-8")
    stats["predictions_file"] = str(pred_file)
    stats["patches_dir"] = str(out)
    return stats


def collect_patches_glob(experiment_dir: str, patches_dir: str, model_name: str) -> dict:
    """Fallback collector when experiment dir has nested timestamp folders only."""
    expr = Path(experiment_dir).resolve()
    task_dirs = [
        p
        for p in glob(pjoin(str(expr), "*"))
        if (Path(p) / "meta.json").is_file()
    ]
    if task_dirs:
        return collect_patches_from_run(expr, patches_dir, model_name=model_name)

    nested = [
        p
        for p in glob(pjoin(str(expr), "*", "*"))
        if (Path(p) / "meta.json").is_file()
    ]
    if nested:
        return collect_patches_from_run(expr, patches_dir, model_name=model_name)

    return collect_patches_from_run(expr, patches_dir, model_name=model_name)
