"""v3.3 decision-trace recorder for calibration-loop forks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.spec_parser.schema import DecisionNode, ScriptDecisionTrace


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionTraceRecorder:
    def __init__(
        self,
        *,
        task_id: str = "",
        parser_version: str = "3.3.0",
        output_dir: Path | None = None,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled
        self.output_dir = output_dir
        self.trace = ScriptDecisionTrace(
            task_id=task_id,
            parser_version=parser_version,
        )

    def record(
        self,
        *,
        node_id: str,
        round_no: int,
        options: list[str],
        decision: str,
        reason: str = "",
        policy_id: str = "",
        evidence_refs: list[str] | None = None,
        action: str = "",
        outcome: str = "",
        evaluation: dict[str, Any] | None = None,
        context_snapshot: dict[str, Any] | None = None,
    ) -> DecisionNode:
        node = DecisionNode(
            node_id=node_id,
            round_no=round_no,
            timestamp=_now_iso(),
            context_snapshot=context_snapshot or {},
            options=list(options),
            evaluation=evaluation or {},
            policy_id=policy_id,
            decision=decision,
            reason=reason,
            evidence_refs=list(evidence_refs or []),
            action=action,
            outcome=outcome,
        )
        if self.enabled:
            self.trace.nodes.append(node)
            self.flush()
        return node

    def set_final(self, *, final_action: str, selected_draft_id: str = "") -> None:
        self.trace.final_action = final_action
        self.trace.selected_draft_id = selected_draft_id
        self.flush()

    def flush(self) -> None:
        if not self.enabled or self.output_dir is None:
            return
        path = self.output_dir / "script_decision_trace.json"
        path.write_text(self.trace.model_dump_json(indent=2))


def should_early_stop(
    history: list[dict[str, Any]],
    *,
    stub_rounds: int = 2,
) -> bool:
    """True when last N rounds share same stub-like blocking and no behavioral ACs."""
    if stub_rounds < 1 or len(history) < stub_rounds:
        return False
    tail = history[-stub_rounds:]
    blocking_sets = [frozenset(r.get("blocking_rules") or []) for r in tail]
    if len(set(blocking_sets)) != 1:
        return False
    if any(int(r.get("behavioral_ac_count") or 0) > 0 for r in tail):
        return False
    stub_markers = {
        "L10-EXISTENCE-ONLY",
        "L12-STUB-AC",
        "L14-EMPTY-FAIL",
    }
    return bool(blocking_sets[0] & stub_markers)
