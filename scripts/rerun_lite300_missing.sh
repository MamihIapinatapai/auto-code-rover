#!/usr/bin/env bash
# Rerun only missing / failed L2 tasks for one repo (no -f wipe), then re-organize predictions.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

REPO="${REPO:-}"
if [[ -z "$REPO" ]]; then
  echo "Usage: REPO=<repo> bash scripts/rerun_lite300_missing.sh [--include-failed-buckets]"
  exit 1
fi

INCLUDE_BUCKETS=0
for arg in "$@"; do
  case "$arg" in
    --include-failed-buckets) INCLUDE_BUCKETS=1 ;;
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
TASKS_FILE="conf/lite300_tasks/${REPO}.txt"
MISSING_FILE="conf/lite300_tasks/${REPO}.missing.txt"
EXPECTED="$(lite300_expected_count "$REPO")"

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

BUCKET_ARGS=()
if [[ "$INCLUDE_BUCKETS" -eq 1 ]]; then
  BUCKET_ARGS=(--include-failed-buckets)
fi

python3 scripts/list_lite300_missing.py --repo "$REPO" "${BUCKET_ARGS[@]}" --output "$MISSING_FILE"
MISSING_N="$(grep -cve '^[[:space:]]*$' "$MISSING_FILE" 2>/dev/null || echo 0)"

if [[ "$MISSING_N" -eq 0 ]]; then
  echo "No missing instances for repo=$REPO"
  exit 0
fi

echo "=== Rerun $MISSING_N missing task(s) for repo=$REPO ==="
CONF_FILE="$(lite300_generate_conf "$REPO" "$MISSING_FILE")"
CONF_BASENAME="$(basename "$CONF_FILE")"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Container $CONTAINER_NAME not running"
  exit 1
fi

run_in_container() {
  docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT -e ACR_SKIP_DOCKER_CHECK=1 -e SKIP_EVAL=1 \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

echo "=== L2 agent (incremental, no -f) ==="
run_in_container "python scripts/run.py conf/generated/${CONF_BASENAME}"

echo "=== Repair patch selection ==="
run_in_container "python scripts/complete_l2_patch_selection.py --expr-dir ${EXPR_DIR}"

echo "=== Re-organize + rebuild predictions ==="
run_in_container "python -c \"from app.post_process import organize_and_form_input; organize_and_form_input('${EXPR_DIR}')\""

echo "=== Verify L2 ==="
run_in_container "python scripts/verify_l2_output.py --expr-dir ${EXPR_DIR} --expected ${EXPECTED} --tasks-file ${TASKS_FILE}"

echo "Done rerun repo=$REPO"
