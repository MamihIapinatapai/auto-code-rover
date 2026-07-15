"""Sandbox execution for acceptance scripts."""

from __future__ import annotations

from app import config
from app.spec_parser.calibration_gate import apply_verdict_to_evidence, evaluate_calibration
from app.spec_parser.per_ac_runner import run_per_ac
from app.spec_parser.schema import ExecutionEvidence, SandboxExecutionResult, StructuredSpecification
from app.spec_parser.trace_collector import maybe_collect_trace
from app.spec_parser.validators import build_execution_evidence_from_result, build_execution_result
from app.task import Task


class SandboxExecutor:
    def __init__(self, task: Task) -> None:
        self.task = task

    def execute(
        self, script_content: str, *, enable_trace: bool = True
    ) -> SandboxExecutionResult:
        repro = self.task.execute_reproducer(script_content)
        trace = None
        if enable_trace and config.spec_parser_enable_trace:
            trace = maybe_collect_trace(self.task, script_content)
        return build_execution_result(repro, trace)

    def execute_with_ac_breakdown(
        self,
        script_content: str,
        spec: StructuredSpecification,
        *,
        enable_trace: bool = True,
        lint_report=None,
        issue_text: str = "",
    ) -> ExecutionEvidence:
        result = self.execute(script_content, enable_trace=enable_trace)
        evidence = build_execution_evidence_from_result(
            spec, result, script_content, issue_text=issue_text
        )
        verdict = evaluate_calibration(
            spec, evidence, script_content, lint_report, issue_text=issue_text
        )
        return apply_verdict_to_evidence(evidence, verdict)

    def execute_per_ac(
        self,
        script_content: str,
        spec: StructuredSpecification,
        *,
        lint_report=None,
        issue_text: str = "",
    ) -> ExecutionEvidence:
        del lint_report  # per-AC runs after preflight in agent
        evidence = run_per_ac(self.task, script_content, spec, issue_text=issue_text)
        verdict = evaluate_calibration(
            spec, evidence, script_content, None, issue_text=issue_text
        )
        return apply_verdict_to_evidence(evidence, verdict)
