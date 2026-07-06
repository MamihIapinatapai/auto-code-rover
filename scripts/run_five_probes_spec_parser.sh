#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER="${ACR_DOCKER_CONTAINER:-pengxm-acr-replicate}"
PROBE_DIR="${PROBE_DIR:-experiment/spec_parser_probe}"
MODEL="${SPEC_PARSER_MODEL:-litellm-generic-deepseek/deepseek-chat}"
SETUP_MAP="${SETUP_MAP:-/opt/SWE-bench/setup_result/setup_map.json}"
TASKS_MAP="${TASKS_MAP:-/opt/SWE-bench/setup_result/tasks_map.json}"
STOP_AFTER="${STOP_AFTER:-full}"

mkdir -p "$ROOT/$PROBE_DIR"
RUN_CMD="cd /workspace/acr && export ACR_SYMPY_PIPELINE_V2=0 && export PYTHONPATH=/workspace/acr"

while IFS= read -r INSTANCE || [[ -n "$INSTANCE" ]]; do
  [[ -z "$INSTANCE" || "$INSTANCE" =~ ^# ]] && continue
  echo "========== $INSTANCE =========="
  set +e
  docker exec "$CONTAINER" bash -lc "
    $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/run_spec_parser_probe.py \
      --instance-id '$INSTANCE' \
      --output-dir /workspace/acr/$PROBE_DIR \
      --setup-map '$SETUP_MAP' \
      --tasks-map '$TASKS_MAP' \
      --model '$MODEL' \
      --stop-after '$STOP_AFTER'
  " 2>&1 | tee "$ROOT/$PROBE_DIR/${INSTANCE}_run.log"
  RUN_EXIT=$?
  set -e
  STATUS=completed; ERR=""
  [[ $RUN_EXIT -ne 0 ]] && STATUS=failed && ERR="exit_code=$RUN_EXIT"
  docker exec "$CONTAINER" bash -lc "
    $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/generate_probe_review.py \
      --instance-id '$INSTANCE' --probe-dir /workspace/acr/$PROBE_DIR \
      --run-status '$STATUS' --run-error '$ERR'
  "
done < "$ROOT/conf/lite300_tasks/sympy_five_probes.txt"

docker exec "$CONTAINER" bash -lc "
  $RUN_CMD && /root/miniconda3/bin/conda run -n auto-code-rover python scripts/eval_spec_parser.py \
    --probe-dir /workspace/acr/$PROBE_DIR
"
echo "Done: $ROOT/$PROBE_DIR"
