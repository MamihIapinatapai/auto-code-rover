#!/usr/bin/env bash
# Single-repo Lite 300 pipeline: L2 → repair → verify → L3 → Feishu Baseline upload.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

REPO="${REPO:-}"
if [[ -z "$REPO" ]]; then
  echo "Usage: REPO=<repo> bash scripts/run_lite300_repo.sh [--resume] [--l2-only] [--skip-upload] [--skip-feishu] [--skip-verify]"
  echo "  Repos: ${LITE300_REPOS[*]}"
  exit 1
fi

RESUME_FLAG=""
L2_ONLY=0
SKIP_UPLOAD=0
SKIP_FEISHU=0
SKIP_VERIFY=0
for arg in "$@"; do
  case "$arg" in
    --resume) RESUME_FLAG="--resume" ;;
    --l2-only) L2_ONLY=1 ;;
    --skip-upload) SKIP_UPLOAD=1 ;;
    --skip-feishu) SKIP_FEISHU=1 ;;
    --skip-verify) SKIP_VERIFY=1 ;;
    *)
      echo "Unknown argument: $arg"
      exit 1
      ;;
  esac
done

if [[ ! " ${LITE300_REPOS[*]} " =~ " ${REPO} " ]]; then
  echo "Unknown REPO: $REPO"
  exit 1
fi

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
EXPR_DIR="$(lite300_expr_dir "$REPO")"
SYNC_DIR="$(lite300_sync_dir "$REPO")"
TASKS_FILE="conf/lite300_tasks/${REPO}.txt"
EXPECTED="$(lite300_expected_count "$REPO")"
CONF_FILE="$(lite300_generate_conf "$REPO")"
CONF_BASENAME="$(basename "$CONF_FILE")"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "ERROR: DEEPSEEK_API_KEY not set. Run: source scripts/source_env.sh"
  exit 1
fi
export ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}"
NUM_PROCESSES="$(lite300_num_processes "$REPO")"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Container $CONTAINER_NAME not running. Start with: bash scripts/run_pilot_docker.sh"
  exit 1
fi

run_in_container() {
  docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT -e ACR_SKIP_DOCKER_CHECK=1 -e SKIP_EVAL=1 \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

echo "=== Lite 300 repo=$REPO expected=$EXPECTED ==="
echo "  expr:  $EXPR_DIR"
echo "  sync:  $SYNC_DIR"
echo "  conf:  $CONF_FILE"

if [[ -z "$RESUME_FLAG" ]]; then
  echo "=== L2 agent (num_processes=${NUM_PROCESSES}, -f) ==="
  run_in_container "python scripts/run.py conf/generated/${CONF_BASENAME} -f"

  echo "=== Repair patch selection + verify L2 ==="
  run_in_container "python scripts/complete_l2_patch_selection.py --expr-dir ${EXPR_DIR}"
  if [[ "$SKIP_VERIFY" -eq 1 ]]; then
    echo "Skipping verify_l2_output (--skip-verify)"
  else
    run_in_container "python scripts/verify_l2_output.py --expr-dir ${EXPR_DIR} --expected ${EXPECTED} --tasks-file ${TASKS_FILE}"
  fi
else
  echo "=== Skipping L2 (--resume: L3 only) ==="
fi

if [[ "$L2_ONLY" -eq 1 ]]; then
  echo "=== --l2-only: skipping L3 and Feishu ==="
  exit 0
fi

echo "=== L3 incremental eval ==="
EXPR_DIR="$EXPR_DIR" SYNC_DIR="$SYNC_DIR" bash scripts/run_pilot_eval_incremental.sh $RESUME_FLAG

if [[ "$SKIP_UPLOAD" -eq 1 || "$SKIP_FEISHU" -eq 1 ]]; then
  echo "Skipping Feishu upload (--skip-upload / --skip-feishu)"
  exit 0
fi

echo "=== Feishu Baseline dry-run ==="
SYSTEM_VERSION="${SYSTEM_VERSION:-Baseline}" \
  DRY_RUN=1 \
  REPO="$REPO" \
  bash scripts/lite300_upload.sh

echo "=== Feishu Baseline upload ==="
SYSTEM_VERSION="${SYSTEM_VERSION:-Baseline}" \
  REPO="$REPO" \
  bash scripts/lite300_upload.sh

echo "Done repo=$REPO → $ROOT/$SYNC_DIR/"
