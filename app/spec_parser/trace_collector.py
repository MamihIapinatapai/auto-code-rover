"""Optional dynamic call trace collection (stub for P3)."""

from __future__ import annotations

MAX_TRACE_EVENTS = 5000


def maybe_collect_trace(task, script_content: str):
    """Trace collection disabled in initial rollout; returns None."""
    return None
