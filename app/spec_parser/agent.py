"""Specification parsing agent orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from loguru import logger
from tenacity import retry, stop_after_attempt

from app import config
from app.agents.agent_common import InvalidLLMResponse
from app.data_structures import MessageThread
from app.infrastructure.shared_memory import SharedMemoryStore
from app.model.gpt import common
from app.spec_parser import evidence_fusion, repo_enrichment, spec_refiner
from app.spec_parser.memory_writer import save_all_artifacts, save_thread
from app.spec_parser.parser_prompts import (
    ISSUE_STRUCTURING_SYSTEM_PROMPT,
    format_issue_structuring_user,
)
from app.spec_parser.repo_context import build_repo_context
from app.spec_parser.schema import StructuredSpecification, TaskType
from app.spec_parser.script_generator import ScriptGenerator
from app.spec_parser.script_prompts import format_feedback
from app.spec_parser.sandbox_executor import SandboxExecutor
from app.spec_parser.validators import (
    extract_failure_anchor,
    validate_ac_calibration,
    validate_structured_spec_semantics,
)
from app.task import Task

StopAfter = Literal["extract", "enrich", "fusion", "calibration", "full"]


class SpecParsingAgent:
    def __init__(self, task: Task, output_dir: str) -> None:
        self.task = task
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.script_generator = ScriptGenerator(task, str(output_dir))
        self.sandbox = SandboxExecutor(task)

    def run(
        self,
        issue_text: str,
        *,
        stop_after: StopAfter = "full",
        use_llm_for_script: bool = True,
    ) -> StructuredSpecification:
        repo_ctx = build_repo_context(self.task)
        draft, extract_thread = self._extract_and_structure(issue_text, repo_ctx)
        save_thread(self.output_dir, extract_thread, "extract")

        enrichment = None
        if config.spec_parser_enable_repo_enrichment:
            enrichment, resolution = repo_enrichment.run(
                self.task, issue_text, repo_ctx, draft, self.output_dir
            )
            (self.output_dir / SharedMemoryStore.REPO_ENRICHMENT_FILENAME).write_text(
                enrichment.model_dump_json(indent=2)
            )
            (
                self.output_dir / SharedMemoryStore.TARGET_RESOLUTION_FILENAME
            ).write_text(resolution.model_dump_json(indent=2))

        spec = spec_refiner.merge(draft, enrichment)
        if stop_after == "enrich":
            self._persist(spec, issue_text)
            return spec

        feedback: str | None = None
        max_rounds = config.spec_parser_max_calibration_rounds
        for rnd in range(1, max_rounds + 1):
            script, gen_thread = self.script_generator.generate(
                spec,
                repo_ctx,
                feedback=feedback,
                round_no=rnd,
                use_llm=use_llm_for_script,
            )
            save_thread(self.output_dir, gen_thread, f"script_round_{rnd}")

            if stop_after == "fusion":
                spec.repro_script = script
                self._persist(spec, issue_text)
                return spec

            evidence = self.sandbox.execute_with_ac_breakdown(
                script.content, spec, enable_trace=True
            )
            spec.execution_evidence = evidence
            passed, reason, failed_ac, uncovered = validate_ac_calibration(
                spec, evidence, script.content
            )
            spec.repro_script = script.with_calibration(
                passed=passed,
                round_no=rnd,
                exit_code=evidence.overall_exit_code,
                stderr_excerpt=evidence.per_criterion_results[0].stderr_excerpt
                if evidence.per_criterion_results
                else "",
            )
            if passed:
                spec.failure_anchor = extract_failure_anchor(
                    spec.repro_script.stderr_excerpt, spec
                )
                break
            feedback = format_feedback(
                round_no=rnd,
                exit_code=evidence.overall_exit_code,
                validation_reason=reason,
                failed_criteria_ids=failed_ac,
                uncovered_co_fix=uncovered,
                stderr_truncated=spec.repro_script.stderr_excerpt,
            )
            logger.info("Spec parser calibration round {} failed: {}", rnd, reason)

        if stop_after == "calibration":
            self._persist(spec, issue_text)
            return spec

        spec = evidence_fusion.merge(spec, enrichment, spec.execution_evidence)
        self._persist(spec, issue_text)
        return spec

    def _persist(self, spec: StructuredSpecification, issue_text: str) -> None:
        swm = SharedMemoryStore.build_from_task(self.task, issue_text, spec)
        SharedMemoryStore.write(self.output_dir, swm)
        save_all_artifacts(self.output_dir, spec)
        logger.info("Spec parser wrote SWM to {}", self.output_dir)

    @retry(stop=stop_after_attempt(5), reraise=True)
    def _extract_and_structure(
        self, issue_text: str, repo_ctx
    ) -> tuple[StructuredSpecification, MessageThread]:
        thread = MessageThread()
        thread.add_system(ISSUE_STRUCTURING_SYSTEM_PROMPT)
        thread.add_user(format_issue_structuring_user(issue_text, repo_ctx))
        response, *_ = common.SELECTED_MODEL.call(
            thread.to_msg(), response_format="json_object"
        )
        thread.add_model(response)
        try:
            data = json.loads(response)
        except json.JSONDecodeError as e:
            raise InvalidLLMResponse(f"Invalid JSON from issue structuring: {e}") from e

        if "goals" in data and "repair_goals" not in data:
            data["repair_goals"] = data.pop("goals")
        if not data.get("repair_goals") and data.get("symptom_goals"):
            data["repair_goals"] = list(data["symptom_goals"])

        spec = StructuredSpecification.model_validate(data)
        validate_structured_spec_semantics(spec, issue_text)
        return spec, thread
