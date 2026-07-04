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

# timeout for test cmd execution, currently set to 5 min
test_exec_timeout: int = 300

models: list[str] = []

backup_model = ["litellm-generic-deepseek/deepseek-chat"]

disable_angelic: bool = False
