#!/usr/bin/env bash
# Run five probes twice: deterministic P2 vs ScopePlan LLM (spec parser full, pre-search).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${ACR_DOCKER_CONTAINER:-pengxm-acr-replicate}"
MODEL="${SPEC_PARSER_MODEL:-litellm-generic-deepseek/deepseek-chat}"
SETUP_MAP="${SETUP_MAP:-/opt/SWE-bench/setup_result/setup_map.json}"
TASKS_MAP="${TASKS_MAP:-/opt/SWE-bench/setup_result/tasks_map.json}"
STOP_AFTER="${STOP_AFTER:-full}"
TASK_LIST="$ROOT/conf/lite300_tasks/sympy_five_probes.txt"

RUN_CMD="cd /workspace/acr && export ACR_SYMPY_PIPELINE_V2=0 && export PYTHONPATH=/workspace/acr"

run_mode() {
  local tag="$1"
  local probe_dir="$2"
  local scope_flag="$3"
  mkdir -p "$ROOT/$probe_dir"
  echo "========== MODE: $tag -> $probe_dir =========="
  while IFS= read -r INSTANCE || [[ -n "$INSTANCE" ]]; do
    [[ -z "$INSTANCE" || "$INSTANCE" =~ ^# ]] && continue
    echo "---- $tag / $INSTANCE ----"
    set +e
    docker exec "$CONTAINER" bash -lc "
      $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/run_spec_parser_probe.py \
        --instance-id '$INSTANCE' \
        --output-dir /workspace/acr/$probe_dir \
        --setup-map '$SETUP_MAP' \
        --tasks-map '$TASKS_MAP' \
        --model '$MODEL' \
        --stop-after '$STOP_AFTER' \
        $scope_flag
    " 2>&1 | tee "$ROOT/$probe_dir/${INSTANCE}_run.log"
    RUN_EXIT=$?
    set -e
    STATUS=completed; ERR=""
    [[ $RUN_EXIT -ne 0 ]] && STATUS=failed && ERR="exit_code=$RUN_EXIT"
    docker exec "$CONTAINER" bash -lc "
      $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/generate_probe_review.py \
        --instance-id '$INSTANCE' --probe-dir /workspace/acr/$probe_dir \
        --run-status '$STATUS' --run-error '$ERR'
    " || true
  done < "$TASK_LIST"

  docker exec "$CONTAINER" bash -lc "
    $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/eval_spec_parser.py \
      --probe-dir /workspace/acr/$probe_dir \
      --output /workspace/acr/$probe_dir/spec_parser_eval_report.json
  "
}

run_mode "deterministic" "spec_parser_probe_v2_det" ""
run_mode "scope_llm" "spec_parser_probe_v2_scope_llm" "--spec-parser-scope-llm"

docker exec "$CONTAINER" bash -lc "
  $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/compare_p2_probe_modes.py \
    --det-dir /workspace/acr/spec_parser_probe_v2_det \
    --scope-dir /workspace/acr/spec_parser_probe_v2_scope_llm \
    --output /workspace/acr/spec_parser_probe_p2_compare_report.json
"
echo "Done. Reports under spec_parser_probe_v2_* and spec_parser_probe_p2_compare_report.json"
