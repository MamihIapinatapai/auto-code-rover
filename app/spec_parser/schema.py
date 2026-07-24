"""Pydantic schemas for the specification parsing agent."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class TaskType(str, Enum):
    BUG_FIX = "BUG_FIX"
    FEATURE = "FEATURE"


class ConstraintKind(str, Enum):
    ENVIRONMENT = "environment"
    BUILD = "build"
    TEST = "test"
    IMPLICIT_HISTORY = "implicit_history"
    API_COMPAT = "api_compat"


class Constraint(BaseModel):
    kind: ConstraintKind
    description: str
    source: Literal["explicit", "implicit"] = "explicit"
    evidence_quote: str = ""


class FixScope(BaseModel):
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    co_fix_required: list[str] = Field(default_factory=list)
    prerequisite: list[str] = Field(default_factory=list)


class ArchitectureHint(BaseModel):
    layer: Literal[
        "guard",
        "bracket_decision",
        "formatter",
        "delegate_chain",
        "core_logic",
        "dimension_clamp",
        "unknown",
    ] = "unknown"
    pattern: Literal[
        "delegate_ast",
        "neighbor_template",
        "minimal_guard",
        "dimension_clamp",
        "inline_forbidden",
        "unknown",
    ] = "unknown"
    neighbor_reference: str | None = None


class IssueCompleteness(BaseModel):
    reporter_drafts: list[str] = Field(default_factory=list)
    symptom_vs_root_gap: str = ""
    completeness: Literal["full", "partial", "ambiguous"] = "ambiguous"


class NegativeConstraint(BaseModel):
    description: str
    rationale: str


class AcceptanceCriterion(BaseModel):
    id: str
    description: str
    check_type: Literal[
        "assertion",
        "exception",
        "return_value",
        "no_regression",
        "behavioral",
    ]
    observable: str
    priority: Literal["must", "should"] = "must"
    covers_entity: str = ""
    criterion_role: Literal[
        "fail_to_pass",
        "no_regression_sentinel",
        "generalization",
    ] = "fail_to_pass"


class StackFrame(BaseModel):
    file: str
    line: int
    function: str = ""
    code_context: str = ""


class FailureAnchor(BaseModel):
    anchor_type: Literal[
        "inferred", "assertion_error", "exception", "trace"
    ] = "inferred"
    exception_type: str | None = None
    message: str | None = None
    top_frame_file: str | None = None
    top_frame_line: int | None = None
    named_entities: list[str] = Field(default_factory=list)
    stack_frames: list[StackFrame] = Field(default_factory=list)


class TraceEvent(BaseModel):
    event: Literal["call", "line", "return", "exception"]
    filename: str
    lineno: int
    funcname: str = ""


class DynamicCallTrace(BaseModel):
    events: list[TraceEvent] = Field(default_factory=list)
    truncated: bool = False
    entry_function: str = "main"


class ReproScriptArtifact(BaseModel):
    filename: str
    content: str
    calibration_passed: bool = False
    calibration_round: int = 0
    exit_code: int | None = None
    stderr_excerpt: str = ""

    def with_calibration(
        self,
        *,
        passed: bool,
        round_no: int,
        exit_code: int | None,
        stderr_excerpt: str,
    ) -> ReproScriptArtifact:
        return self.model_copy(
            update={
                "calibration_passed": passed,
                "calibration_round": round_no,
                "exit_code": exit_code,
                "stderr_excerpt": stderr_excerpt[:4000],
            }
        )


class CriterionResult(BaseModel):
    criterion_id: str
    passed_on_buggy_code: bool
    expected_failure: bool = True
    message: str = ""
    stderr_excerpt: str = ""
    skipped_reason: str | None = None


class ExecutionEvidence(BaseModel):
    calibration_passed: bool = False
    overall_exit_code: int | None = None
    per_criterion_results: list[CriterionResult] = Field(default_factory=list)
    primary_failure_ac_id: str | None = None
    calibration_error: str | None = None
    execution_mode: Literal["holistic", "per_ac"] = "holistic"
    preflight_passed: bool = True


class ScriptLintReport(BaseModel):
    passed: bool = True
    blocking_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    ac_section_map: dict[str, list[int]] = Field(default_factory=dict)
    missing_ac_ids: list[str] = Field(default_factory=list)


class ReviewBlockingFix(BaseModel):
    rule: str = ""
    bad_pattern: str = ""
    legal_rewrite: str = ""
    why_legal: str = ""


class ReviewIssueGap(BaseModel):
    kind: str = ""  # missing_must | weak_assert | over_spec_risk
    detail: str = ""
    legal_rewrite: str = ""
    superseded_by_blocking: bool = False


class ReviewDiagnosis(BaseModel):
    failure_class: str = "none"  # lint|gate_feature|gate_env|mixed|none
    summary: str = ""


class ReviewGateFix(BaseModel):
    kind: str = "other"  # intentional_ac_fail|not_implemented|env_not_script|other
    evidence: str = ""
    legal_rewrite: str = ""
    why: str = ""


class IssueCoverageItem(BaseModel):
    """Single Issue Must/Should ↔ AC binding (v3.3 evidence chain)."""

    issue_item_id: str = ""
    issue_quote: str = ""
    ac_id: str | None = None
    expected_layer: str = "any"  # api|cli|web|http|library|any
    actual_layer: str = "unknown"
    product_calls: list[str] = Field(default_factory=list)
    assertion_strength: str = "unknown"
    evidence_type: str = "unknown"
    verdict: str = "unknown"  # covered|partial|missing|over_spec|deferred
    legal_rewrite: str = ""
    issue_quote_span_hint: str = ""


class IssueCoverageChain(BaseModel):
    round_no: int = 1
    stage: Literal["preflight", "gate", "post_pass"] = "preflight"
    items: list[IssueCoverageItem] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    source: str = "reviewer_llm"


class DecisionNode(BaseModel):
    node_id: str = ""
    round_no: int = 1
    timestamp: str = ""
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    options: list[str] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    policy_id: str = ""
    decision: str = ""
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    action: str = ""
    outcome: str = ""


class ScriptDecisionTrace(BaseModel):
    task_id: str = ""
    parser_version: str = "3.3.0"
    nodes: list[DecisionNode] = Field(default_factory=list)
    final_action: str = ""
    selected_draft_id: str = ""


class DraftMetrics(BaseModel):
    draft_id: str = ""
    round_no: int = 1
    script_content: str = ""
    lint_violations: int = 0
    blocking_rules: list[str] = Field(default_factory=list)
    behavioral_ac_count: int = 0
    existence_only_ac_count: int = 0
    empty_fail_ac_count: int = 0
    calibration_passed: bool = False
    coverage_missing_must: int = 0
    coverage_wrong_layer: int = 0
    anchor_signature_violations: int = 0
    anchor_layer_gap_count: int = 0
    # v3.4 score terms
    concrete_expect_ac_count: int = 0
    recipe_compliance_bonus: int = 0
    scc_m_pass: bool = False
    contract_path_s1: bool = False
    feature_calib_ok: bool = False
    false_fail_risk_hits: int = 0
    harness_error: int = 0
    score: float = 0.0


class AnchorSymbol(BaseModel):
    """One Issue/AC-named symbol grounded in the repo (non-test)."""

    name: str
    kind: str = "unknown"
    module_hint: str = ""
    rel_path: str = ""
    lineno: int | None = None
    signature_ast: str = ""
    is_async: bool = False
    docstring_head: str = ""
    signature_runtime: str = ""
    docstring_runtime: str = ""
    public_export: bool | None = None
    source: str = "issue"
    confidence: float = 0.0
    ambiguous: bool = False
    alternate_paths: list[str] = Field(default_factory=list)


class AnchorEntrypoint(BaseModel):
    """CLI / console / coarse HTTP hints (not a full router map)."""

    kind: str
    name: str = ""
    target: str = ""
    rel_path: str = ""
    evidence: str = ""
    confidence: float = 0.0


class ScriptAnchor(BaseModel):
    task_id: str = ""
    parser_version: str = "3.3.1"
    package_roots: list[str] = Field(default_factory=list)
    symbols: list[AnchorSymbol] = Field(default_factory=list)
    entrypoints: list[AnchorEntrypoint] = Field(default_factory=list)
    layer_hints: dict[str, str] = Field(default_factory=dict)
    missing_issue_symbols: list[str] = Field(default_factory=list)
    build_errors: list[str] = Field(default_factory=list)
    tier1_ok: bool = False
    tier2_ok: bool = False
    tier2_skipped_reason: str = ""



class ScriptReviewReport(BaseModel):
    """v3.2+ script-reviewer output (advisory; lint/Gate remain authoritative)."""

    stage: Literal["preflight", "gate"] = "preflight"
    round_no: int = 1
    diagnosis: ReviewDiagnosis = Field(default_factory=ReviewDiagnosis)
    blocking_fixes: list[ReviewBlockingFix] = Field(default_factory=list)
    gate_fixes: list[ReviewGateFix] = Field(default_factory=list)
    issue_alignment: list[ReviewIssueGap] = Field(default_factory=list)
    deferred_issue_gaps: list[str] = Field(default_factory=list)
    ordered_actions: list[str] = Field(default_factory=list)
    issue_coverage_chain: list[IssueCoverageItem] = Field(default_factory=list)
    decision_summary: dict[str, Any] = Field(default_factory=dict)
    raw_response: str = ""
    parse_ok: bool = True
    sanitized: bool = False


class RepoEnrichment(BaseModel):
    target_files: list[str] = Field(default_factory=list)
    missing_handlers: list[str] = Field(default_factory=list)
    co_fix_candidates: list[str] = Field(default_factory=list)
    neighbor_reference: str | None = None
    architecture_pattern: str = "unknown"
    negative_patterns: list[str] = Field(default_factory=list)
    search_api_hints: list[str] = Field(default_factory=list)
    evidence_snippets: dict[str, str] = Field(default_factory=dict)
    context_domain: str = ""
    enrichment_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class AnalysisScope(BaseModel):
    files: list[str] = Field(default_factory=list)
    classes: list[str] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    visitors: list[str] = Field(default_factory=list)
    expand_siblings: bool = False
    missing_symbols: list[str] = Field(default_factory=list)
    context_domain: str = ""


class ScopePlanRecord(BaseModel):
    used_llm: bool = False
    fallback: bool = False
    validated: bool = False
    raw_plan: dict | None = None


class TargetResolutionArtifact(BaseModel):
    entities: list[dict] = Field(default_factory=list)
    candidates: list[dict] = Field(default_factory=list)
    analysis_scope: AnalysisScope = Field(default_factory=AnalysisScope)
    scope_plan: ScopePlanRecord = Field(default_factory=ScopePlanRecord)


class StructuredSpecification(BaseModel):
    task_type: TaskType
    summary: str
    symptom_goals: list[str] = Field(default_factory=list)
    repair_goals: list[str] = Field(min_length=1)
    constraints: list[Constraint] = Field(default_factory=list)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    fix_scope: FixScope = Field(default_factory=FixScope)
    architecture_hint: ArchitectureHint = Field(default_factory=ArchitectureHint)
    issue_completeness: IssueCompleteness = Field(
        default_factory=IssueCompleteness
    )
    negative_constraints: list[NegativeConstraint] = Field(default_factory=list)
    failure_anchor: FailureAnchor | None = None
    repro_script: ReproScriptArtifact | None = None
    dynamic_call_trace: DynamicCallTrace | None = None
    execution_evidence: ExecutionEvidence | None = None
    repo_enrichment: RepoEnrichment | None = None
    issue_noise_filtered: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    parser_version: str = "2.2.0"

    @field_validator("repair_goals", mode="before")
    @classmethod
    def _coerce_goals(cls, v: list[str] | None) -> list[str]:
        if v is None:
            return []
        return [str(x) for x in v if str(x).strip()]


class RepoContext(BaseModel):
    repo_name: str
    python_version: str | None = None
    conda_env: str | None = None
    test_framework: str = "unknown"
    sample_test_files: list[str] = Field(default_factory=list)
    top_level_packages: list[str] = Field(default_factory=list)
    sample_test_excerpt: str = ""


class SandboxExecutionResult(BaseModel):
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    reproduced: bool = False
    trace: DynamicCallTrace | None = None


class SharedWorkingMemory(BaseModel):
    instance_id: str
    repo: str
    problem_statement_hash: str
    structured_spec: StructuredSpecification
    created_at: str
    spec_parser_threads: list[str] = Field(default_factory=list)
    schema_version: str = "1.1.0"
    spec_source: str = "spec_parser"
