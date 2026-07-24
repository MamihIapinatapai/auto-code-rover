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
from app.spec_parser import contract_refiner, evidence_fusion, repo_enrichment, spec_refiner
from app.spec_parser.calibration_gate import (
    classify_gate_failure_kind,
    classify_gate_triage,
    feature_signal_ok,
)
from app.spec_parser.artifact_store import write_artifact_consistency_report
from app.spec_parser.contract_path import run_contract_pipeline
from app.spec_parser.coverage_heuristics import run_coverage_heuristics
from app.spec_parser.decision_trace import DecisionTraceRecorder, should_early_stop
from app.spec_parser.draft_picker import (
    best_draft_overall,
    build_draft_metrics,
    persist_candidate,
    pick_best_draft,
)
from app.spec_parser.evidence_chain import build_coverage_chain
from app.spec_parser.memory_writer import save_all_artifacts, save_thread
from app.spec_parser.parser_prompts import (
    ISSUE_STRUCTURING_SYSTEM_PROMPT,
    format_issue_structuring_user,
)
from app.spec_parser.pipeline import (
    effective_parser_version,
    is_v3_pipeline,
    should_run_repo_enrichment,
)
from app.spec_parser.repair_draft import build_repair_draft, save_repair_draft
from app.spec_parser.repo_context import build_repo_context
from app.spec_parser.schema import DraftMetrics, ScriptAnchor, StructuredSpecification
from app.spec_parser.script_anchor import (
    build_tier1,
    detect_layer_gaps,
    format_anchor_for_prompt,
    persist_anchor,
)
from app.spec_parser.script_anchor_inspect import enrich_tier2, should_run_tier2
from app.spec_parser.script_generator import ScriptGenerator
from app.spec_parser.script_prompts import format_feedback
from app.spec_parser.script_prompts_v3 import format_feedback_v3
from app.spec_parser.script_reviewer import ScriptReviewer, format_review_feedback
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
        self.script_reviewer = ScriptReviewer()

    def _build_failure_feedback(
        self,
        *,
        spec: StructuredSpecification,
        script_content: str,
        issue_text: str,
        round_no: int,
        stage: str,
        lint_report,
        validation_reason: str,
        failed_criteria_ids: list[str],
        stderr_excerpt: str = "",
        exit_code: int | None = None,
        uncovered_co_fix: list[str] | None = None,
        use_llm_for_script: bool = True,
        base_script_note: str = "",
    ) -> str:
        """v3.2/v3.3: optional script reviewer; fallback to format_feedback_v3 / v2."""
        want_review = bool(
            getattr(config, "spec_parser_enable_script_review", False)
        )
        if stage == "preflight":
            want_review = want_review and bool(
                getattr(config, "spec_parser_script_review_on_preflight", True)
            )
        elif stage == "gate":
            want_review = want_review and bool(
                getattr(config, "spec_parser_script_review_on_gate", True)
            )

        feedback = ""
        if want_review and config.spec_parser_use_v3_prompts:
            try:
                review, review_thread = self.script_reviewer.review(
                    issue_text=issue_text,
                    script_content=script_content,
                    task_type=spec.task_type,
                    stage=stage,
                    round_no=round_no,
                    lint_report=lint_report,
                    validation_reason=validation_reason,
                    failed_criteria_ids=failed_criteria_ids,
                    stderr_excerpt=stderr_excerpt,
                    exit_code=exit_code,
                    use_llm=use_llm_for_script,
                )
                (self.output_dir / f"script_review_round_{round_no}.json").write_text(
                    review.model_dump_json(indent=2)
                )
                save_thread(
                    self.output_dir, review_thread, f"script_review_round_{round_no}"
                )
                if review.issue_coverage_chain and getattr(
                    config, "spec_parser_enable_evidence_chain", True
                ):
                    chain = build_coverage_chain(
                        review.issue_coverage_chain,
                        round_no=round_no,
                        stage=stage,
                    )
                    (
                        self.output_dir / f"issue_coverage_chain_round_{round_no}.json"
                    ).write_text(chain.model_dump_json(indent=2))
                if (
                    review.parse_ok
                    or review.ordered_actions
                    or review.blocking_fixes
                    or review.gate_fixes
                    or review.issue_coverage_chain
                ):
                    feedback = format_review_feedback(
                        review,
                        validation_reason=validation_reason,
                        blocking_rules=(
                            list(lint_report.blocking_rules) if lint_report else None
                        ),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Script review degraded to rule feedback: {}", exc
                )

        if not feedback:
            if config.spec_parser_use_v3_prompts:
                feedback = format_feedback_v3(
                    task_type=spec.task_type,
                    round_no=round_no,
                    stage=stage,  # type: ignore[arg-type]
                    validation_reason=validation_reason,
                    failed_criteria_ids=failed_criteria_ids,
                    stderr_truncated=stderr_excerpt,
                )
            else:
                feedback = format_feedback(
                    round_no=round_no,
                    exit_code=exit_code,
                    validation_reason=validation_reason,
                    failed_criteria_ids=failed_criteria_ids,
                    uncovered_co_fix=list(
                        uncovered_co_fix
                        if uncovered_co_fix is not None
                        else spec.fix_scope.co_fix_required
                    ),
                    stderr_truncated=stderr_excerpt,
                )

        if base_script_note:
            feedback = base_script_note + "\n\n" + feedback
        return feedback

    def run(
        self,
        issue_text: str,
        *,
        stop_after: StopAfter = "full",
        use_llm_for_script: bool = True,
    ) -> StructuredSpecification:
        v3 = is_v3_pipeline()
        repo_ctx = build_repo_context(self.task)
        draft, extract_thread = self._extract_and_structure(issue_text, repo_ctx)
        draft = contract_refiner.refine(draft, issue_text)
        draft.parser_version = effective_parser_version()
        save_thread(self.output_dir, extract_thread, "extract")

        enrichment = None
        if should_run_repo_enrichment(stop_after):
            enrichment, resolution = repo_enrichment.run(
                self.task, issue_text, repo_ctx, draft, self.output_dir
            )
            (self.output_dir / SharedMemoryStore.REPO_ENRICHMENT_FILENAME).write_text(
                enrichment.model_dump_json(indent=2)
            )
            (
                self.output_dir / SharedMemoryStore.TARGET_RESOLUTION_FILENAME
            ).write_text(resolution.model_dump_json(indent=2))

        if v3:
            if config.spec_parser_use_repair_draft:
                save_repair_draft(
                    self.output_dir, build_repair_draft(draft, issue_text)
                )
            spec = spec_refiner.merge_v3(draft)
        else:
            spec = spec_refiner.merge(draft, enrichment)
        if stop_after == "enrich":
            self._persist(spec, issue_text)
            return spec

        feedback: str | None = None
        max_rounds = config.spec_parser_max_calibration_rounds
        must_ids = [ac.id for ac in spec.acceptance_criteria if ac.priority == "must"]
        decision_enabled = bool(
            getattr(config, "spec_parser_enable_decision_trace", False)
        )
        best_of = bool(getattr(config, "spec_parser_enable_draft_best_of", False))
        early_rounds = int(
            getattr(config, "spec_parser_early_stop_stub_rounds", 2) or 2
        )
        decision = DecisionTraceRecorder(
            task_id=getattr(self.task, "task_id", "") or "",
            parser_version=effective_parser_version(),
            output_dir=self.output_dir,
            enabled=decision_enabled,
        )
        candidates: list[DraftMetrics] = []
        round_history: list[dict] = []
        early_stopped = False

        # --- v3.3.1 ScriptAnchor Tier1 (B1: independent of repo_enrichment) ---
        script_anchor: ScriptAnchor | None = None
        anchor_block = ""
        layer_gaps: list[str] = []
        if getattr(config, "spec_parser_enable_script_anchor", False):
            script_anchor = build_tier1(
                project_path=self.task.project_path,
                issue_text=issue_text,
                spec=spec,
                task_id=getattr(self.task, "task_id", "") or "",
                package_roots=list(repo_ctx.top_level_packages or []),
            )
            persist_anchor(self.output_dir, script_anchor)
            layer_gaps = detect_layer_gaps(issue_text, script_anchor)
            decision.record(
                node_id="D_anchor_build",
                round_no=0,
                options=["ok", "partial", "empty"],
                decision=(
                    "ok"
                    if script_anchor.tier1_ok
                    else ("partial" if script_anchor.symbols else "empty")
                ),
                reason=(
                    f"symbols={len(script_anchor.symbols)} "
                    f"entrypoints={len(script_anchor.entrypoints)}"
                ),
                policy_id="anchor_tier1_v331",
                evidence_refs=["script_anchor.json"],
                action="continue_generate",
            )
            if layer_gaps:
                decision.record(
                    node_id="D_anchor_layer_gap",
                    round_no=0,
                    options=["ok", "layer_unknown"],
                    decision="layer_unknown",
                    reason=",".join(layer_gaps),
                    policy_id="anchor_layer_v331",
                    evidence_refs=[f"gap:{g}" for g in layer_gaps],
                    action="feedback_only",
                )
            anchor_block = format_anchor_for_prompt(script_anchor)
            if layer_gaps:
                anchor_block += (
                    "\n### Layer gaps (do not fake lower-level API as sole CLI/Web check)\n"
                    + "\n".join(f"- {g}" for g in layer_gaps)
                )

        for rnd in range(1, max_rounds + 1):
            script, gen_thread = self.script_generator.generate(
                spec,
                repo_ctx,
                issue_text=issue_text,
                feedback=feedback,
                round_no=rnd,
                use_llm=use_llm_for_script,
                script_anchor_block=anchor_block,
            )
            save_thread(self.output_dir, gen_thread, f"script_round_{rnd}")

            if stop_after == "fusion":
                spec.repro_script = script
                self._persist(spec, issue_text)
                return spec

            lint_report = None
            if config.spec_parser_script_preflight:
                from app.spec_parser.script_linter import lint_feedback, preflight

                lint_report = preflight(spec, script.content, issue_text=issue_text)
                (self.output_dir / f"script_lint_round_{rnd}.json").write_text(
                    lint_report.model_dump_json(indent=2)
                )
                if getattr(config, "spec_parser_wrong_layer_warnings", True):
                    heuristics = run_coverage_heuristics(
                        script.content,
                        must_ids=must_ids,
                        layer_hints=(
                            script_anchor.layer_hints if script_anchor else None
                        ),
                        entrypoint_names=(
                            [ep.name for ep in script_anchor.entrypoints]
                            if script_anchor
                            else None
                        ),
                    )
                    (
                        self.output_dir / f"coverage_heuristics_round_{rnd}.json"
                    ).write_text(json.dumps(heuristics, indent=2))
                else:
                    heuristics = {"wrong_layer_count": 0, "warnings": []}

                metrics = build_draft_metrics(
                    round_no=rnd,
                    script_content=script.content,
                    lint_report=lint_report,
                    calibration_passed=False,
                    must_ids=must_ids,
                    coverage_wrong_layer=int(heuristics.get("wrong_layer_count") or 0),
                )
                metrics.anchor_layer_gap_count = len(layer_gaps)
                candidates.append(metrics)
                persist_candidate(self.output_dir, metrics)
                round_history.append(
                    {
                        "blocking_rules": list(lint_report.blocking_rules),
                        "behavioral_ac_count": metrics.behavioral_ac_count,
                    }
                )

                if not lint_report.passed:
                    stub_rules = {
                        "L10-EXISTENCE-ONLY",
                        "L12-STUB-AC",
                        "L14-EMPTY-FAIL",
                    }
                    hit_stub = bool(stub_rules & set(lint_report.blocking_rules))
                    use_contract = bool(
                        getattr(config, "spec_parser_enable_behavior_contract", False)
                    ) and (
                        bool(getattr(config, "spec_parser_force_contract_path", False))
                        or (
                            hit_stub
                            and bool(getattr(config, "spec_parser_s1_on_stub", True))
                        )
                    )
                    if use_contract:
                        decision.record(
                            node_id="D_persist",
                            round_no=rnd,
                            options=["persist", "reject_regen", "contract_path"],
                            decision="contract_path",
                            reason=lint_feedback(lint_report),
                            policy_id="stub_to_contract_v34",
                            evidence_refs=[
                                f"lint:{r}" for r in lint_report.blocking_rules
                            ],
                            action="contract_path",
                        )
                        cp = run_contract_pipeline(
                            output_dir=self.output_dir,
                            issue_text=issue_text,
                            anchor_summary=anchor_block,
                            decision=decision,
                            use_llm=use_llm_for_script,
                            issue_kind=str(
                                getattr(spec.task_type, "value", spec.task_type)
                            ),
                            task_id=getattr(self.task, "task_id", "") or "",
                        )
                        if cp.get("ok") and cp.get("script"):
                            from app.spec_parser.schema import ReproScriptArtifact
                            from app.spec_parser.script_linter import (
                                lint_feedback as _lf,
                            )
                            from app.spec_parser.script_linter import preflight as _pf

                            script_content = cp["script"]
                            # Thin lint on contract path (L10c semantics: repair not free-regen)
                            thin = _pf(spec, script_content, issue_text=issue_text)
                            (self.output_dir / "script_lint_contract.json").write_text(
                                thin.model_dump_json(indent=2)
                            )
                            # Execute contract script
                            if config.spec_parser_ac_isolated_run:
                                evidence = self.sandbox.execute_per_ac(
                                    script_content,
                                    spec,
                                    lint_report=thin,
                                    issue_text=issue_text,
                                )
                            else:
                                evidence = self.sandbox.execute_with_ac_breakdown(
                                    script_content,
                                    spec,
                                    enable_trace=True,
                                    lint_report=thin,
                                    issue_text=issue_text,
                                )
                            spec.execution_evidence = evidence
                            stderr = ""
                            if evidence.per_criterion_results:
                                stderr = (
                                    evidence.per_criterion_results[0].stderr_excerpt
                                    or ""
                                )
                            triage = classify_gate_triage(
                                spec.task_type,
                                stderr,
                                script_content,
                                issue_text=issue_text,
                                exit_code=evidence.overall_exit_code,
                                stdout="",
                            )
                            decision.record(
                                node_id="D_gate_classify",
                                round_no=rnd,
                                options=[
                                    "missing_third_party",
                                    "missing_feature_module",
                                    "harness_error",
                                    "feature_fail",
                                    "pass",
                                ],
                                decision=triage,
                                reason=f"triage={triage}",
                                policy_id="gate_triage_v34",
                                action="continue",
                            )
                            passed, reason, failed_ac, uncovered = (
                                validate_ac_calibration(
                                    spec,
                                    evidence,
                                    script_content,
                                    thin if thin.passed else None,
                                    issue_text=issue_text,
                                )
                            )
                            # O2: feature module signal is not ordinary calib_pass
                            feature_ok = passed and triage == "feature_fail"
                            if triage == "missing_feature_module":
                                feature_ok = False
                                passed = False
                                reason = f"feature_signal_ok (not calib_pass): {reason}"
                            if triage in ("missing_third_party", "harness_error"):
                                passed = False
                            scc = cp.get("scc") or {}
                            recipe_bonus = 0
                            for it in (cp.get("contract") or {}).get("items") or []:
                                if it.get("recipe_id"):
                                    recipe_bonus = 1
                                    break
                            metrics_cp = build_draft_metrics(
                                round_no=rnd,
                                script_content=script_content,
                                lint_report=thin,
                                calibration_passed=feature_ok,
                                must_ids=must_ids,
                                concrete_expect_ac_count=len(
                                    (cp.get("contract") or {}).get("items") or []
                                ),
                                recipe_compliance_bonus=recipe_bonus,
                                scc_m_pass=bool(scc.get("scc_m_pass")),
                                contract_path_s1=True,
                                feature_calib_ok=feature_ok,
                                harness_error=1
                                if triage == "harness_error"
                                else 0,
                            )
                            candidates.append(metrics_cp)
                            persist_candidate(self.output_dir, metrics_cp)
                            spec.repro_script = ReproScriptArtifact(
                                filename="test_feature.py",
                                content=script_content,
                                calibration_passed=feature_ok,
                                calibration_round=rnd,
                                exit_code=evidence.overall_exit_code,
                                stderr_excerpt=stderr,
                            )
                            if feature_ok:
                                decision.record(
                                    node_id="D_persist",
                                    round_no=rnd,
                                    options=["persist", "reject_regen"],
                                    decision="persist",
                                    reason="contract_path feature_calib_ok",
                                    policy_id="contract_calib_v34",
                                    action="calib_pass",
                                )
                                break
                            # Accept degraded S1 script even if not calib (O1) when forbid_no_script
                            if getattr(
                                config, "spec_parser_forbid_no_script_if_s1_ok", True
                            ) and (cp.get("contract") or {}).get("items"):
                                decision.record(
                                    node_id="D_pick_draft",
                                    round_no=rnd,
                                    options=["s1_accept", "no_script"],
                                    decision="s1_accept",
                                    reason="degraded_or_uncalib_s1_kept",
                                    policy_id="s1_accept_v34",
                                    action="s1_accept",
                                )
                                # keep script; finalize later as s1 path
                                early_stopped = False
                                break
                        # contract path failed → no_script
                        decision.record(
                            node_id="D_early_stop",
                            round_no=rnd,
                            options=["continue", "no_script"],
                            decision="no_script",
                            reason=cp.get("reason") or "contract_path_failed",
                            policy_id="contract_fail_v34",
                            action="no_script",
                        )
                        early_stopped = True
                        break

                    decision.record(
                        node_id="D_persist",
                        round_no=rnd,
                        options=["persist", "reject_regen", "reject_no_script"],
                        decision="reject_regen",
                        reason=lint_feedback(lint_report),
                        policy_id="l14_empty_fail_v33"
                        if "L14-EMPTY-FAIL" in lint_report.blocking_rules
                        else "preflight_lint",
                        evidence_refs=[
                            f"lint:{r}" for r in lint_report.blocking_rules
                        ],
                        action="regen",
                    )
                    if should_early_stop(round_history, stub_rounds=early_rounds):
                        decision.record(
                            node_id="D_early_stop",
                            round_no=rnd,
                            options=["continue", "no_script"],
                            decision="no_script",
                            reason="same stub-like blocking for consecutive rounds",
                            policy_id="early_stop_stub_v33",
                            action="no_script",
                        )
                        early_stopped = True
                        logger.info(
                            "Spec parser early-stop NO_SCRIPT after round {}", rnd
                        )
                        break

                    base_note = ""
                    if best_of:
                        best_prev = best_draft_overall(candidates)
                        if (
                            best_prev
                            and best_prev.round_no != rnd
                            and best_prev.score > metrics.score
                        ):
                            excerpt = best_prev.script_content[:4000]
                            base_note = (
                                "## BASE_SCRIPT_TO_IMPROVE "
                                f"(draft {best_prev.draft_id}, score={best_prev.score})\n"
                                "Prefer improving this draft rather than rewriting from scratch.\n"
                                f"```python\n{excerpt}\n```"
                            )
                    feedback = self._build_failure_feedback(
                        spec=spec,
                        script_content=script.content,
                        issue_text=issue_text,
                        round_no=rnd,
                        stage="preflight",
                        lint_report=lint_report,
                        validation_reason=lint_feedback(lint_report),
                        failed_criteria_ids=lint_report.missing_ac_ids,
                        use_llm_for_script=use_llm_for_script,
                        base_script_note=base_note,
                    )
                    logger.info("Spec parser preflight round {} failed", rnd)
                    continue
            else:
                metrics = build_draft_metrics(
                    round_no=rnd,
                    script_content=script.content,
                    lint_report=None,
                    calibration_passed=False,
                    must_ids=must_ids,
                )
                candidates.append(metrics)
                persist_candidate(self.output_dir, metrics)

            if config.spec_parser_ac_isolated_run:
                evidence = self.sandbox.execute_per_ac(
                    script.content, spec, lint_report=lint_report, issue_text=issue_text
                )
            else:
                evidence = self.sandbox.execute_with_ac_breakdown(
                    script.content,
                    spec,
                    enable_trace=True,
                    lint_report=lint_report,
                    issue_text=issue_text,
                )
            spec.execution_evidence = evidence

            # Tier2 inspect AFTER sandbox (B3: serves regen only; never blocks first gen)
            if (
                script_anchor is not None
                and getattr(config, "spec_parser_enable_script_anchor_tier2", False)
            ):
                # Treat non-ENV calibration_error absence + packages present as ok-to-try
                sandbox_ok_import = not (
                    evidence.calibration_error
                    and "ENV" in (evidence.calibration_error or "")
                )
                if should_run_tier2(script_anchor, sandbox_ok_import):
                    script_anchor = enrich_tier2(
                        script_anchor, project_path=self.task.project_path
                    )
                    persist_anchor(self.output_dir, script_anchor)
                    decision.record(
                        node_id="D_anchor_inspect",
                        round_no=rnd,
                        options=["enriched", "degraded", "skipped"],
                        decision=(
                            "enriched"
                            if script_anchor.tier2_ok
                            else "degraded"
                        ),
                        reason=script_anchor.tier2_skipped_reason or "ok",
                        policy_id="anchor_inspect_v331",
                        action="regen_prompt_update",
                    )
                    # Refresh prompt block for next round with runtime signatures
                    anchor_block = format_anchor_for_prompt(script_anchor)
                    if layer_gaps:
                        anchor_block += (
                            "\n### Layer gaps\n"
                            + "\n".join(f"- {g}" for g in layer_gaps)
                        )
                else:
                    decision.record(
                        node_id="D_anchor_inspect",
                        round_no=rnd,
                        options=["enriched", "degraded", "skipped"],
                        decision="skipped",
                        reason="sandbox_not_ready_or_disabled",
                        policy_id="anchor_inspect_v331",
                        action="skip",
                    )

            stderr = ""
            if evidence.per_criterion_results:
                stderr = evidence.per_criterion_results[0].stderr_excerpt or ""
            gate_kind = classify_gate_failure_kind(
                spec.task_type,
                stderr,
                script.content,
                issue_text=issue_text,
                exit_code=evidence.overall_exit_code,
            )
            decision.record(
                node_id="D_gate_classify",
                round_no=rnd,
                options=[
                    "env_failure",
                    "feature_not_implemented",
                    "feature_regression",
                    "pass",
                ],
                decision={
                    "env": "env_failure",
                    "feature": "feature_not_implemented",
                    "mixed": "feature_regression",
                    "syntax": "env_failure",
                    "none": "pass",
                }.get(gate_kind, gate_kind),
                reason=f"gate_kind={gate_kind}",
                policy_id="gate_env_v33",
                evidence_refs=[f"stderr:{stderr[:200]}"],
                action="calib_fail" if gate_kind == "env" else "continue",
            )

            # PersistGuard: re-check L14 even if lint somehow missed it
            from app.spec_parser.script_linter import preflight as _preflight

            recheck = _preflight(spec, script.content, issue_text=issue_text)
            if not recheck.passed and "L14-EMPTY-FAIL" in recheck.blocking_rules:
                decision.record(
                    node_id="D_persist",
                    round_no=rnd,
                    options=["persist", "reject_regen"],
                    decision="reject_regen",
                    reason="L14-EMPTY-FAIL on PersistGuard recheck",
                    policy_id="l14_empty_fail_v33",
                    evidence_refs=["lint:L14-EMPTY-FAIL"],
                    action="regen",
                )
                feedback = self._build_failure_feedback(
                    spec=spec,
                    script_content=script.content,
                    issue_text=issue_text,
                    round_no=rnd,
                    stage="preflight",
                    lint_report=recheck,
                    validation_reason="L14-EMPTY-FAIL PersistGuard",
                    failed_criteria_ids=recheck.missing_ac_ids,
                    use_llm_for_script=use_llm_for_script,
                )
                continue

            passed, reason, failed_ac, uncovered = validate_ac_calibration(
                spec, evidence, script.content, lint_report, issue_text=issue_text
            )
            # Update last candidate with calib result
            if candidates and candidates[-1].round_no == rnd:
                candidates[-1].calibration_passed = passed
                from app.spec_parser.draft_picker import score_draft

                candidates[-1].score = score_draft(candidates[-1])
                persist_candidate(self.output_dir, candidates[-1])

            spec.repro_script = script.with_calibration(
                passed=passed,
                round_no=rnd,
                exit_code=evidence.overall_exit_code,
                stderr_excerpt=stderr,
            )
            if passed:
                decision.record(
                    node_id="D_persist",
                    round_no=rnd,
                    options=["persist", "reject_regen"],
                    decision="persist",
                    reason="calibration_passed",
                    policy_id="calib_pass",
                    action="calib_pass",
                )
                spec.failure_anchor = extract_failure_anchor(
                    spec.repro_script.stderr_excerpt, spec
                )
                break
            reason_full = reason
            if uncovered:
                reason_full = f"{reason}; uncovered co_fix: {uncovered}"
            feedback = self._build_failure_feedback(
                spec=spec,
                script_content=script.content,
                issue_text=issue_text,
                round_no=rnd,
                stage="gate",
                lint_report=lint_report,
                validation_reason=reason_full,
                failed_criteria_ids=failed_ac,
                stderr_excerpt=spec.repro_script.stderr_excerpt,
                exit_code=evidence.overall_exit_code,
                uncovered_co_fix=uncovered,
                use_llm_for_script=use_llm_for_script,
            )
            logger.info("Spec parser calibration round {} failed: {}", rnd, reason)

        # Best-of / early-stop finalization
        if early_stopped:
            decision.set_final(final_action="no_script", selected_draft_id="")
            if spec.repro_script is not None:
                spec.repro_script = spec.repro_script.with_calibration(
                    passed=False,
                    round_no=spec.repro_script.calibration_round or 0,
                    exit_code=spec.repro_script.exit_code,
                    stderr_excerpt=spec.repro_script.stderr_excerpt or "",
                )
        elif best_of and candidates:
            best = pick_best_draft(candidates)
            score_policy = (
                "draft_score_v34"
                if getattr(config, "spec_parser_draft_score_version", "") == "v34"
                else "draft_score_v33"
            )
            if best is not None:
                action = (
                    "calib_pass"
                    if best.calibration_passed
                    else ("s1_accept" if best.contract_path_s1 else "persist")
                )
                decision.record(
                    node_id="D_pick_draft",
                    round_no=best.round_no,
                    options=[c.draft_id for c in candidates],
                    decision=best.draft_id,
                    reason=f"score={best.score}",
                    policy_id=score_policy,
                    evaluation={"scores": {c.draft_id: c.score for c in candidates}},
                    action=action,
                )
                decision.set_final(
                    final_action=action
                    if action in ("calib_pass", "s1_accept")
                    else "calib_pass",
                    selected_draft_id=best.draft_id,
                )
                # Restore best script content into repro_script if different
                if (
                    spec.repro_script is None
                    or spec.repro_script.content != best.script_content
                ):
                    from app.spec_parser.schema import ReproScriptArtifact

                    fname = (
                        spec.repro_script.filename
                        if spec.repro_script is not None
                        else "test_feature.py"
                    )
                    spec.repro_script = ReproScriptArtifact(
                        filename=fname,
                        content=best.script_content,
                        calibration_passed=bool(best.calibration_passed),
                        calibration_round=best.round_no,
                    )
            else:
                # Keep contract S1 script if present even without calib
                if (
                    spec.repro_script
                    and getattr(config, "spec_parser_forbid_no_script_if_s1_ok", True)
                    and (self.output_dir / "behavior_contract.json").exists()
                ):
                    decision.set_final(
                        final_action="s1_accept", selected_draft_id="contract"
                    )
                else:
                    decision.set_final(final_action="no_script", selected_draft_id="")
        else:
            if spec.repro_script and spec.repro_script.calibration_passed:
                decision.set_final(
                    final_action="calib_pass",
                    selected_draft_id=f"r{spec.repro_script.calibration_round}",
                )
            elif (
                spec.repro_script
                and (self.output_dir / "behavior_contract.json").exists()
                and getattr(config, "spec_parser_forbid_no_script_if_s1_ok", True)
            ):
                decision.set_final(
                    final_action="s1_accept", selected_draft_id="contract"
                )
            else:
                decision.set_final(final_action="no_script", selected_draft_id="")

        # ART consistency
        try:
            write_artifact_consistency_report(
                self.output_dir,
                final_action=decision.trace.final_action
                if decision.enabled
                else (
                    "calib_pass"
                    if spec.repro_script and spec.repro_script.calibration_passed
                    else "no_script"
                ),
                selected_draft_id=decision.trace.selected_draft_id
                if decision.enabled
                else "",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("artifact consistency report failed: {}", exc)

        if stop_after == "calibration":
            self._persist(spec, issue_text)
            return spec

        if v3:
            spec = evidence_fusion.merge_v3(spec, spec.execution_evidence)
        else:
            spec = evidence_fusion.merge(spec, enrichment, spec.execution_evidence)
        self._persist(spec, issue_text)
        return spec

    def _persist(self, spec: StructuredSpecification, issue_text: str) -> None:
        swm = SharedMemoryStore.build_from_task(self.task, issue_text, spec)
        SharedMemoryStore.write(self.output_dir, swm)
        save_all_artifacts(self.output_dir, spec)
        # Re-apply ART after persist (save_all_artifacts may rewrite scripts)
        try:
            from app.spec_parser.decision_trace import DecisionTraceRecorder

            final_action = "unknown"
            selected = ""
            trace_path = self.output_dir / "script_decision_trace.json"
            if trace_path.exists():
                import json as _json

                data = _json.loads(trace_path.read_text(encoding="utf-8"))
                final_action = data.get("final_action") or final_action
                selected = data.get("selected_draft_id") or ""
            write_artifact_consistency_report(
                self.output_dir,
                final_action=final_action,
                selected_draft_id=selected,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("post-persist ART failed: {}", exc)
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
