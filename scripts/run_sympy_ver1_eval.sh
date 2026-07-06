#!/usr/bin/env bash
# [AutoCodeRover-ver1] Full SymPy L2 → L3 targeted eval (77 instances)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
EXPR_DIR="experiment/deepseek-lite-300-ver1/repos/sympy"
SYNC_DIR="lite300_output_ver1/repos/sympy"
CONF_FILE="conf/deepseek-lite-300-ver1.sympy.conf"
NUM_PROCESSES="${NUM_PROCESSES:-1}"
EVAL_WORKERS="${EVAL_WORKERS:-1}"
RESUME_FLAG=""

for arg in "$@"; do
  case "$arg" in
    --resume) RESUME_FLAG="--resume" ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: bash scripts/run_sympy_ver1_eval.sh [--resume]" >&2
      exit 1
      ;;
  esac
done

export SYSTEM_VERSION=ver1
export ACR_SEMANTIC_INJECTION_VER1=1

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
export ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Container $CONTAINER_NAME not running. Start with: bash scripts/run_pilot_docker.sh"
  exit 1
fi

run_in_container() {
  docker exec \
    -e DEEPSEEK_API_KEY \
    -e ACR_TOKEN_LIMIT \
    -e ACR_SKIP_DOCKER_CHECK=1 \
    -e ACR_SEMANTIC_INJECTION_VER1=1 \
    -e SKIP_EVAL=1 \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

echo "[AutoCodeRover-ver1] === SymPy full L2 agent (num_processes=${NUM_PROCESSES}) ==="
if [[ -z "$RESUME_FLAG" ]]; then
  run_in_container "python scripts/run.py ${CONF_FILE} -f"
  run_in_container "python scripts/complete_l2_patch_selection.py --expr-dir ${EXPR_DIR}"
  run_in_container "python scripts/verify_l2_output.py --expr-dir ${EXPR_DIR} --expected 77 --tasks-file conf/lite300_tasks/sympy.txt"
else
  echo "[AutoCodeRover-ver1] --resume: skipping L2, L3 only"
fi

echo "[AutoCodeRover-ver1] === L3 incremental eval (workers=${EVAL_WORKERS}) ==="
docker exec \
  -e DEEPSEEK_API_KEY \
  -e ACR_SKIP_DOCKER_CHECK=1 \
  -e HOST_ACR_ROOT="$ROOT" \
  -e PRUNE_AUTOCODEROVER_IMAGES="${PRUNE_AUTOCODEROVER_IMAGES:-0}" \
  "$CONTAINER_NAME" bash -lc "
    source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr &&
    bash scripts/setup_swe_bench_docker.sh &&
    python scripts/run_eval_incremental.py --expr-dir /workspace/acr/${EXPR_DIR} ${RESUME_FLAG} --num-processes ${EVAL_WORKERS}
  "

mkdir -p "$ROOT/$SYNC_DIR"
docker cp "$CONTAINER_NAME:/workspace/acr/${EXPR_DIR}/." "$ROOT/$SYNC_DIR/"
echo "[AutoCodeRover-ver1] Synced to $ROOT/$SYNC_DIR/"

python3 "$ROOT/scripts/generate_ver1_sympy_report.py"
echo "[AutoCodeRover-ver1] Report: document/output_analysis/sympy/sympy_ver1_run_report.md"

if [[ "${SKIP_FEISHU:-0}" == "1" ]]; then
  echo "[AutoCodeRover-ver1] Skipping Feishu upload (SKIP_FEISHU=1)"
  exit 0
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi
UPLOAD="${ROOT}/scripts/upload_results.py"

echo "[AutoCodeRover-ver1] === Feishu ver1 dry-run ==="
SYSTEM_VERSION=ver1 DRY_RUN=1 \
  "$PYTHON" "$UPLOAD" \
  --system_version ver1 \
  --log_path "$ROOT/$SYNC_DIR" \
  --dry-run

echo "[AutoCodeRover-ver1] === Feishu ver1 upload ==="
SYSTEM_VERSION=ver1 \
  "$PYTHON" "$UPLOAD" \
  --system_version ver1 \
  --log_path "$ROOT/$SYNC_DIR"

echo "[AutoCodeRover-ver1] Feishu upsert complete (系统版本=ver1, log_path=$SYNC_DIR)"
