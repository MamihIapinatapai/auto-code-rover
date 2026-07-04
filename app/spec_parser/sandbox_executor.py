"""Sandbox execution for acceptance scripts."""

from __future__ import annotations

from app import config
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
    ) -> ExecutionEvidence:
        result = self.execute(script_content, enable_trace=enable_trace)
        return build_execution_evidence_from_result(spec, result, script_content)

    def execute_per_ac(
        self, script_content: str, spec: StructuredSpecification
    ) -> ExecutionEvidence:
        return self.execute_with_ac_breakdown(script_content, spec, enable_trace=False)
