#!/usr/bin/env bash
# DeepSWE Python-subset agent run inside yuntongzhang/auto-code-rover:experiment
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
IMAGE="yuntongzhang/auto-code-rover:experiment"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
CONF_FILE="${DEEPSWE_CONF:-conf/deepseek-deepswe.conf}"
LOG_FILE="${DEEPSWE_LOG:-$ROOT/outputs/deepswe_docker_run.log}"
MAX_TASKS="${DEEPSWE_MAX_TASKS:-0}"

mkdir -p "$ROOT/outputs"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "ERROR: DEEPSEEK_API_KEY is not set in conf/.env"
  exit 1
fi
export ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}"

if [[ ! -f "$ROOT/third_party/deep-swe/tasks/manifest.json" ]]; then
  echo "DeepSWE tasks missing. Running setup..."
  bash "$ROOT/scripts/setup_deepswe.sh"
fi

echo "=== Pull experiment image (if missing) ==="
if ! docker image inspect "$IMAGE" &>/dev/null; then
  docker pull "$IMAGE"
fi

echo "=== Start or reuse container: $CONTAINER_NAME ==="
if docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    docker start "$CONTAINER_NAME"
  fi
else
  docker run -d --name "$CONTAINER_NAME" --entrypoint "" \
    -v "$ROOT:/workspace/acr" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -e DEEPSEEK_API_KEY \
    -e ACR_TOKEN_LIMIT \
    "$IMAGE" \
    sleep infinity
fi

run_in_container() {
  docker exec \
    -e DEEPSEEK_API_KEY \
    -e ACR_TOKEN_LIMIT \
    -e ACR_SKIP_DOCKER_CHECK=1 \
    -e DEEPSWE_MAX_TASKS="$MAX_TASKS" \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

echo "=== Verify DeepSWE paths inside container ==="
run_in_container "test -f third_party/deep-swe/tasks/manifest.json && wc -l conf/deepswe_python_tasks.txt"

echo "=== Run DeepSWE Python subset (conf=$CONF_FILE, max_tasks=$MAX_TASKS) ==="
echo "Logging to $LOG_FILE"
run_in_container "python scripts/run_deepswe.py --conf-file $CONF_FILE" 2>&1 | tee "$LOG_FILE"

echo "=== Done. Patches: outputs/deepswe_patches/ ==="
ls -la "$ROOT/outputs/deepswe_patches/" 2>/dev/null | head -20 || true
