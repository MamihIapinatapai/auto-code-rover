#!/usr/bin/env python3
"""Wrapper: delegate to SWE-bench-docker/scripts/upload_results.py (repo root entry)."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_TARGET = Path(__file__).resolve().parent.parent / "SWE-bench-docker" / "scripts" / "upload_results.py"
if not _TARGET.is_file():
    print(f"Missing upload script: {_TARGET}", file=sys.stderr)
    raise SystemExit(1)

sys.argv[0] = str(_TARGET)
runpy.run_path(str(_TARGET), run_name="__main__")
