#!/usr/bin/env bash
# L3 incremental SWE-bench eval (SERVER_REPLICATION_GUIDE §6.1)
# Default: keep preloaded autocoderover/* images; only remove sweb.eval containers after each instance.
# Legacy disk-saving: --prune-preloaded-images or PRUNE_AUTOCODEROVER_IMAGES=1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
EXPR_DIR="${EXPR_DIR:-experiment/deepseek-lite-pilot}"
SYNC_DIR="${SYNC_DIR:-pilot_output}"
RESUME_FLAG=""
REPORT_ONLY_FLAG=""
PRUNE_PRELOADED_FLAG=""
INSTANCE_ARGS=()
EXPR_DIR_FLAG="--expr-dir /workspace/acr/${EXPR_DIR}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --resume) RESUME_FLAG="--resume"; shift ;;
    --report-only) REPORT_ONLY_FLAG="--report-only"; shift ;;
    --prune-preloaded-images) PRUNE_PRELOADED_FLAG="--prune-preloaded-images"; shift ;;
    --instance-id)
      shift
      [[ $# -gt 0 ]] || { echo "Missing value for --instance-id"; exit 1; }
      INSTANCE_ARGS+=("--instance-id" "$1")
      shift
      ;;
    --expr-dir)
      echo "Usage: EXPR_DIR=experiment/your-id $0 [--resume] [--report-only] [--prune-preloaded-images] [--instance-id ID ...]"
      exit 1
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Usage: $0 [--resume] [--report-only] [--prune-preloaded-images] [--instance-id ID ...]"
      exit 1
      ;;
  esac
done

if ((${#INSTANCE_ARGS[@]})); then
  INSTANCE_STR="${INSTANCE_ARGS[*]}"
else
  INSTANCE_STR=""
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Container $CONTAINER_NAME not running. Start with: bash scripts/run_pilot_docker.sh"
  exit 1
fi

CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"

if [[ -n "$PRUNE_PRELOADED_FLAG" ]]; then
  export PRUNE_AUTOCODEROVER_IMAGES=1
fi

docker exec -e DEEPSEEK_API_KEY -e ACR_SKIP_DOCKER_CHECK=1 -e HOST_ACR_ROOT="$ROOT" \
  -e PRUNE_AUTOCODEROVER_IMAGES="${PRUNE_AUTOCODEROVER_IMAGES:-0}" \
  "$CONTAINER_NAME" bash -lc "
  source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr &&
  bash scripts/setup_swe_bench_docker.sh &&
  python scripts/run_eval_incremental.py $EXPR_DIR_FLAG $RESUME_FLAG $REPORT_ONLY_FLAG ${PRUNE_PRELOADED_FLAG:-} $INSTANCE_STR
"

mkdir -p "$ROOT/$SYNC_DIR"
docker cp "$CONTAINER_NAME:/workspace/acr/${EXPR_DIR}/." "$ROOT/$SYNC_DIR/"
echo "Synced to $ROOT/$SYNC_DIR/ (from ${EXPR_DIR})"
