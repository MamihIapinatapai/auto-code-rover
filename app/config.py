"""
Values of global configuration variables.
"""

# Overall output directory for results
output_dir: str = ""

# Max number of times context retrieval and all is tried
overall_retry_limit: int = 3

# upper bound of the number of conversation rounds for the agent
conv_round_limit: int = 15

# whether to perform sbfl
enable_sbfl: bool = False

# whether to perform our own validation
enable_validation: bool = False

# E1 ablation: only use search_code (no AST APIs)
enable_text_only_search: bool = False

# DeepSWE: primary language of the current task (python, typescript, go, ...)
task_language: str | None = None

# whether to do angelic debugging
enable_angelic: bool = False

# whether to do perfect angelic debugging
enable_perfect_angelic: bool = False


# A special mode to only save SBFL result and exit
only_save_sbfl_result: bool = False

# A special mode to only generate reproducer tests and exit
only_reproduce: bool = False

# A special mode to only evaluate a reproducer test
only_eval_reproducer: bool = False

# Experimental mode to add reproducer and reviewer into the workflow
reproduce_and_review: bool = False

# TODO (ver1): enable SymPy semantic rule injection in search + patch agents
enable_semantic_injection_ver1: bool = True

# v2.2 pipeline: artifact, linters, sibling_scan LLM (SymPy tasks only)
enable_sympy_pipeline_v2: bool = True

# Module 1: specification parsing agent
enable_spec_parser: bool = False
spec_parser_only: bool = False
spec_parser_max_calibration_rounds: int = 3
spec_parser_enable_trace: bool = True
spec_parser_script_timeout_sec: int = 120
spec_parser_enable_repo_enrichment: bool = True
spec_parser_ac_isolated_run: bool = False
spec_parser_skip_legacy_reproducer: bool = False
spec_parser_max_spec_tokens: int = 4000
spec_parser_fusion_require_static_dynamic_agree: bool = True

# v2.0 generic P2 static enrichment
spec_parser_max_resolve_candidates: int = 15
spec_parser_candidate_score_threshold: float = 0.3
spec_parser_symbol_index_cache: bool = True
spec_parser_scope_llm: bool = False
spec_parser_scope_llm_fallback: bool = True
spec_parser_scope_merge_confidence_min: float = 0.6

# v2.1 dynamic calibration (M6–M9)
spec_parser_script_preflight: bool = True
spec_parser_strict_legacy: bool = True
spec_parser_normalize_ac_markers: bool = True
spec_parser_preflight_counts_as_round: bool = False
spec_parser_require_ac_fail_marker: bool = False

# v2.2 Search contract enhancement (M10–M15)
spec_parser_cooccurrence_bonus: float = 3.0
spec_parser_primary_entity_boost: float = 1.2
spec_parser_max_co_fix: int = 8
spec_parser_require_class_in_index_for_issue_class: bool = True
spec_parser_require_primary_class_in_scope: bool = True
spec_parser_search_context_max_snippet_chars: int = 400

# v3.x pipeline (M16+; default remains v2.2 until M20 product cutover)
# Set to "3.1.0" (or any 3.*) to enable v3 pipeline + script-quality gates.
spec_parser_version: str = "2.2.0"
spec_parser_use_repair_draft: bool = True

# v3.1+ script generation prompts (M17+); L10+ quality rules always on in linter.
# Prefer True when running DeepSWE / v3 calib so generators use script_prompts_v3.
spec_parser_use_v3_prompts: bool = True

# v3.2 script reviewer LLM (translate lint/gate + Issue gaps → generator feedback).
# When False, calibration loop falls back to format_feedback_v3 (3.1 behaviour).
spec_parser_enable_script_review: bool = True
spec_parser_script_review_on_preflight: bool = True
spec_parser_script_review_on_gate: bool = True

# v3.3 evidence chain + decision trace + draft best-of
spec_parser_enable_evidence_chain: bool = True
spec_parser_enable_decision_trace: bool = True
spec_parser_enable_draft_best_of: bool = True
spec_parser_early_stop_stub_rounds: int = 2
spec_parser_env_transitive_modules: list[str] = [
    "yaml",
    "typing_extensions",
    "packaging",
    "attrs",
    "idna",
    "certifi",
    "urllib3",
    "charset_normalizer",
    "tomli",
    "tomllib",
]
spec_parser_coverage_post_pass_review: bool = False
spec_parser_wrong_layer_warnings: bool = True

# v3.3.1 ScriptAnchor (Tier1 static + Tier2 inspect)
spec_parser_enable_script_anchor: bool = False
spec_parser_enable_script_anchor_tier2: bool = False
spec_parser_anchor_max_symbols: int = 12
spec_parser_anchor_max_entrypoints: int = 8
spec_parser_anchor_prompt_max_chars: int = 3500
spec_parser_anchor_layer_gap_blocks_persist: bool = False
spec_parser_anchor_scan_decorators: bool = True
spec_parser_anchor_inspect_timeout_sec: int = 10
spec_parser_anchor_pre_gen_inspect: bool = False
spec_parser_anchor_score_signature_weight: float = 0.0  # B5: default off

# v3.4.0 Contract-First / S1 / Gate / ART / Recipe / DSL (FINAL §6)
spec_parser_enable_s1_skeleton: bool = True
spec_parser_enable_behavior_contract: bool = True
spec_parser_contract_schema_version: str = "bc-1"
spec_parser_contract_max_expect_retries: int = 2
spec_parser_force_contract_path: bool = False
spec_parser_enable_contract_llm_review: bool = False
spec_parser_contract_llm_review_mode: str = "high_risk_only"
spec_parser_contract_review_model: str | None = None
spec_parser_contract_llm_review_task_allowlist: list[str] = []
spec_parser_enable_script_contract_align: bool = True
spec_parser_enable_script_contract_llm: bool = False
spec_parser_script_contract_llm_mode: str = "high_risk_only"
spec_parser_scc_share_expect_retries: bool = True
spec_parser_enable_recipe_cards: bool = True
spec_parser_enable_usage_recipe_mine: bool = False
spec_parser_enable_dual_state_lite: bool = True
spec_parser_enable_gate_triage: bool = True
spec_parser_enable_artifact_store: bool = True
spec_parser_contract_path_legacy_review: str = "skip"  # skip | warn_only
spec_parser_s1_on_stub: bool = True
spec_parser_forbid_no_script_if_s1_ok: bool = True
spec_parser_delete_script_on_no_script: bool = True
spec_parser_s1_require_entrypoint_for_cli_web: bool = True
spec_parser_recipe_cards_path: str = "app/spec_parser/recipe_cards"
spec_parser_draft_score_version: str = "v34"
spec_parser_feature_module_name_hints: list[str] = []

# v3.5.0 Real Renderer / UsageMiner / FailureSemantics / PersistGuard (design §9)
spec_parser_enable_usage_miner: bool = True
spec_parser_usage_mine_tests_call_shape: bool = True
spec_parser_usage_mine_budget_files: int = 80
spec_parser_usage_snippet_topk_per_api: int = 3
spec_parser_forbid_renderer_stub: bool = True
spec_parser_enable_failure_semantics_check: bool = True
spec_parser_enable_failure_provenance: bool = True
spec_parser_forbid_bare_raises_exception: bool = True
spec_parser_renderer_scheme: str = "A"
spec_parser_renderer_all_or_nothing: bool = True
spec_parser_enable_bind_mode_signature: bool = False
spec_parser_slot_placeholder_format: str = "__SLOT_{key}__"
spec_parser_s1_require_exec_gate: bool = True
spec_parser_allow_contract_only: bool = True
spec_parser_free_fallback_on_contract_fail: bool = True
spec_parser_persist_rejected_scripts: bool = True
spec_parser_official_script_only: bool = True
spec_parser_contract_json_repair_rounds: int = 2

# timeout for test cmd execution, currently set to 5 min
test_exec_timeout: int = 300

models: list[str] = []

backup_model = ["litellm-generic-deepseek/deepseek-chat"]

disable_angelic: bool = False
