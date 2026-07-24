"""v2.2 vs v3.x spec parser pipeline selection helpers."""

from __future__ import annotations

from app import config

V2_PARSER_VERSION = "2.2.0"
V3_PARSER_VERSION = "3.5.0"


def _enable_v34_defaults() -> None:
    """3.4.0 MVP switches (FINAL §6); do not enable table LLM / SCC-L / UsageRecipe."""
    config.spec_parser_enable_s1_skeleton = True
    config.spec_parser_enable_behavior_contract = True
    config.spec_parser_contract_schema_version = "bc-1"
    config.spec_parser_contract_max_expect_retries = 2
    config.spec_parser_force_contract_path = False
    config.spec_parser_enable_contract_llm_review = False
    config.spec_parser_enable_script_contract_align = True
    config.spec_parser_enable_script_contract_llm = False
    config.spec_parser_scc_share_expect_retries = True
    config.spec_parser_enable_recipe_cards = True
    config.spec_parser_enable_usage_recipe_mine = False
    config.spec_parser_enable_dual_state_lite = True
    config.spec_parser_enable_gate_triage = True
    config.spec_parser_enable_artifact_store = True
    config.spec_parser_contract_path_legacy_review = "skip"
    config.spec_parser_s1_on_stub = True
    config.spec_parser_forbid_no_script_if_s1_ok = True
    config.spec_parser_delete_script_on_no_script = True
    config.spec_parser_s1_require_entrypoint_for_cli_web = True
    config.spec_parser_draft_score_version = "v34"


def _enable_v35_defaults() -> None:
    """3.5.0: UsageMiner + Real Renderer + EG + honest s1 (build on 3.4)."""
    _enable_v34_defaults()
    config.spec_parser_enable_usage_miner = True
    config.spec_parser_usage_mine_tests_call_shape = True
    config.spec_parser_forbid_renderer_stub = True
    config.spec_parser_enable_failure_semantics_check = True
    config.spec_parser_enable_failure_provenance = True
    config.spec_parser_s1_require_exec_gate = True
    config.spec_parser_allow_contract_only = True
    config.spec_parser_renderer_scheme = "A"
    config.spec_parser_enable_bind_mode_signature = False
    config.spec_parser_free_fallback_on_contract_fail = True
    config.spec_parser_enable_contract_llm_review = False
    config.spec_parser_enable_script_contract_llm = False
    config.spec_parser_draft_score_version = "v35"


def is_v3_pipeline() -> bool:
    version = getattr(config, "spec_parser_version", V2_PARSER_VERSION)
    return version.startswith("3")


def effective_parser_version() -> str:
    return getattr(config, "spec_parser_version", V2_PARSER_VERSION)


def should_run_repo_enrichment(stop_after: str) -> bool:
    if stop_after == "extract":
        return False
    return bool(config.spec_parser_enable_repo_enrichment)


def configure_repo_enrichment(
    *,
    stop_after: str,
    no_repo_enrichment: bool = False,
    with_repo_enrichment: bool = False,
) -> None:
    """Resolve P2 (repo_enrichment) for the current run."""
    if no_repo_enrichment:
        config.spec_parser_enable_repo_enrichment = False
        return
    if with_repo_enrichment:
        config.spec_parser_enable_repo_enrichment = True
        return
    if is_v3_pipeline():
        config.spec_parser_enable_repo_enrichment = False
        return
    config.spec_parser_enable_repo_enrichment = stop_after not in ("extract",)


def _enable_v33_chains() -> None:
    config.spec_parser_enable_script_review = True
    config.spec_parser_enable_evidence_chain = True
    config.spec_parser_enable_decision_trace = True
    config.spec_parser_enable_draft_best_of = True


def _disable_anchor() -> None:
    config.spec_parser_enable_script_anchor = False
    config.spec_parser_enable_script_anchor_tier2 = False


def apply_spec_parser_version(version: str | None) -> None:
    if not version:
        return
    config.spec_parser_version = version
    if version.startswith("3"):
        config.spec_parser_use_v3_prompts = True

    # Order matters: 3.5 before 3.4 before 3.3.1 before bare 3.3 (startswith)
    if version.startswith("3.5") or version == "3.5.0":
        _enable_v33_chains()
        config.spec_parser_enable_script_anchor = True
        config.spec_parser_enable_script_anchor_tier2 = True
        _enable_v35_defaults()
    elif version.startswith("3.4") or version == "3.4.0":
        _enable_v33_chains()
        config.spec_parser_enable_script_anchor = True
        config.spec_parser_enable_script_anchor_tier2 = True
        _enable_v34_defaults()
    elif version.startswith("3.3.1") or version == "3.3.1":
        _enable_v33_chains()
        config.spec_parser_enable_script_anchor = True
        config.spec_parser_enable_script_anchor_tier2 = True
        # Keep 3.4 switches off when explicitly on 3.3.1
        config.spec_parser_enable_behavior_contract = False
        config.spec_parser_draft_score_version = "v33"
    elif version.startswith("3.3") or version == "3.3.0":
        _enable_v33_chains()
        _disable_anchor()
    elif version.startswith("3.2") or version == "3.2.0":
        config.spec_parser_enable_script_review = True
        config.spec_parser_enable_evidence_chain = False
        config.spec_parser_enable_decision_trace = False
        config.spec_parser_enable_draft_best_of = False
        _disable_anchor()
    elif version.startswith("3.1") or version in ("3.0.0", "3.1.0"):
        config.spec_parser_enable_script_review = False
        config.spec_parser_enable_evidence_chain = False
        config.spec_parser_enable_decision_trace = False
        config.spec_parser_enable_draft_best_of = False
        _disable_anchor()
