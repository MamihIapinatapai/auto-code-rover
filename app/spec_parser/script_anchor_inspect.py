"""ScriptAnchor Tier2: runtime inspect enrichment (serves regen only by default)."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from loguru import logger

from app import config
from app.spec_parser.schema import ScriptAnchor

_INSPECT_SCRIPT = r'''
import importlib, inspect, json, sys
specs = json.loads(sys.argv[1])
out = []
for item in specs:
    try:
        mod = importlib.import_module(item["module"])
        obj = mod
        for part in item["qualname"].split("."):
            if not part:
                continue
            obj = getattr(obj, part)
        if inspect.isclass(obj):
            target = getattr(obj, "__init__", obj)
        else:
            target = obj
        sig = str(inspect.signature(target))
        doc = (inspect.getdoc(obj) or "").splitlines()
        out.append({
            "name": item["name"],
            "signature_runtime": sig,
            "docstring_runtime": doc[0] if doc else "",
            "ok": True,
        })
    except Exception as e:
        out.append({
            "name": item["name"],
            "ok": False,
            "error": type(e).__name__,
        })
print(json.dumps(out))
'''


def _infer_module_qualname(sym_name: str, package_roots: list[str], rel_path: str) -> tuple[str, str]:
    """Best-effort module + qualname for importlib."""
    # From path: pkg/retort.py -> pkg.retort
    module = ""
    if rel_path.endswith(".py"):
        mod_path = rel_path[:-3].replace("\\", "/").replace("/", ".")
        if mod_path.endswith(".__init__"):
            mod_path = mod_path[: -len(".__init__")]
        module = mod_path
    if not module and package_roots:
        module = package_roots[0]
    parts = sym_name.split(".")
    if len(parts) == 1:
        # class or function in module
        return module, parts[0]
    return module, ".".join(parts)


def should_run_tier2(anchor: ScriptAnchor, sandbox_ok_import: bool) -> bool:
    return bool(
        getattr(config, "spec_parser_enable_script_anchor_tier2", True)
        and sandbox_ok_import
        and anchor.symbols
    )


def enrich_tier2(
    anchor: ScriptAnchor,
    *,
    project_path: str,
    python_executable: str | None = None,
) -> ScriptAnchor:
    """
    Run inspect probe in project cwd. On failure mark degraded (B3: never blocks gen).
    """
    if not anchor.symbols:
        return anchor.model_copy(
            update={"tier2_ok": False, "tier2_skipped_reason": "no_symbols"}
        )

    specs = []
    for sym in anchor.symbols[:12]:
        module, qual = _infer_module_qualname(
            sym.name, anchor.package_roots, sym.rel_path
        )
        if not module:
            continue
        specs.append({"name": sym.name, "module": module, "qualname": qual})
    if not specs:
        return anchor.model_copy(
            update={"tier2_ok": False, "tier2_skipped_reason": "no_module_hints"}
        )

    timeout = int(getattr(config, "spec_parser_anchor_inspect_timeout_sec", 10) or 10)
    import os
    import sys

    py = python_executable or sys.executable or "python3"
    env = os.environ.copy()
    # Prefer project root on PYTHONPATH so package_roots import (evidence: adaptix needs src)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        project_path + (os.pathsep + prev if prev else "")
    )
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix="_anchor_inspect.py", delete=False
        ) as fh:
            fh.write(_INSPECT_SCRIPT)
            script_path = fh.name
        cp = subprocess.run(
            [py, script_path, json.dumps(specs)],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        Path(script_path).unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.info("Tier2 inspect degraded: {}", exc)
        return anchor.model_copy(
            update={
                "tier2_ok": False,
                "tier2_skipped_reason": f"inspect_error:{type(exc).__name__}",
            }
        )

    if cp.returncode != 0 or not cp.stdout.strip():
        return anchor.model_copy(
            update={
                "tier2_ok": False,
                "tier2_skipped_reason": f"inspect_exit:{cp.returncode}:{cp.stderr[:120]}",
            }
        )
    try:
        rows = json.loads(cp.stdout)
    except json.JSONDecodeError:
        return anchor.model_copy(
            update={"tier2_ok": False, "tier2_skipped_reason": "inspect_bad_json"}
        )

    by_name = {r.get("name"): r for r in rows if isinstance(r, dict)}
    new_syms = []
    ok_count = 0
    for sym in anchor.symbols:
        row = by_name.get(sym.name)
        if row and row.get("ok"):
            ok_count += 1
            new_syms.append(
                sym.model_copy(
                    update={
                        "signature_runtime": row.get("signature_runtime") or "",
                        "docstring_runtime": row.get("docstring_runtime") or "",
                    }
                )
            )
        else:
            new_syms.append(sym)
    return anchor.model_copy(
        update={
            "symbols": new_syms,
            "tier2_ok": ok_count > 0,
            "tier2_skipped_reason": "" if ok_count else "all_inspect_failed",
        }
    )
