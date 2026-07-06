#!/usr/bin/env bash
# [AutoCodeRover-ver1] Gap-fill missing L2 → verify → L3 → Feishu
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
EXPR_DIR="experiment/deepseek-lite-300-ver1/repos/sympy"
MISSING_FILE="conf/lite300_tasks/sympy.ver1.missing.txt"
TASK_LIST="/workspace/acr/${EXPR_DIR}/sympy.ver1.missing.txt"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "ERROR: DEEPSEEK_API_KEY not set"
  exit 1
fi

run_in_container() {
  docker exec \
    -e DEEPSEEK_API_KEY \
    -e ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}" \
    -e ACR_SKIP_DOCKER_CHECK=1 \
    -e ACR_SEMANTIC_INJECTION_VER1=1 \
    -e SKIP_EVAL=1 \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

MISSING_N="$(grep -cve '^[[:space:]]*$' "$ROOT/$MISSING_FILE" 2>/dev/null || echo 0)"
if [[ "$MISSING_N" -eq 0 ]]; then
  echo "[AutoCodeRover-ver1] No missing instances; proceeding to L3"
else
  echo "[AutoCodeRover-ver1] === Gap-fill L2 for ${MISSING_N} missing instances ==="
  run_in_container "cp /workspace/acr/${MISSING_FILE} ${TASK_LIST}"
  run_in_container "PYTHONPATH=/workspace/acr python app/main.py swe-bench --reproduce-and-review \
    --setup-map /opt/SWE-bench/setup_result/setup_map.json \
    --tasks-map /opt/SWE-bench/setup_result/tasks_map.json \
    --output-dir /workspace/acr/${EXPR_DIR} \
    --task-list-file ${TASK_LIST} \
    --model litellm-generic-deepseek/deepseek-chat \
    --model-temperature 0.2 \
    --conv-round-limit 10 \
    --num-processes 1 \
    --enable-semantic-injection-ver1 \
    --no-print"
  run_in_container "python scripts/complete_l2_patch_selection.py --expr-dir ${EXPR_DIR}"
  run_in_container "python -c \"from app.post_process import organize_and_form_input; organize_and_form_input('/workspace/acr/${EXPR_DIR}')\""
  run_in_container "python scripts/verify_l2_output.py --expr-dir ${EXPR_DIR} --expected 77 --tasks-file conf/lite300_tasks/sympy.txt"
fi

echo "[AutoCodeRover-ver1] === L3 + sync + report + Feishu ==="
bash "$ROOT/scripts/run_sympy_ver1_eval.sh" --resume
