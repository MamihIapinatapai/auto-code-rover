#!/usr/bin/env bash
# Pilot agent run inside yuntongzhang/auto-code-rover:experiment (SERVER_REPLICATION_GUIDE §5.2)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Group policy: container name must start with username/abbreviation; data under personal dir via bind mount
CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
IMAGE="yuntongzhang/auto-code-rover:experiment"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "ERROR: DEEPSEEK_API_KEY is not set."
  echo "  Recommended: cp conf/.env.example conf/.env && edit conf/.env (gitignored)"
  echo "  Or: export DEEPSEEK_API_KEY=sk-... && export ACR_TOKEN_LIMIT=4096"
  exit 1
fi
export ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}"

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
  docker exec -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT -e ACR_SKIP_DOCKER_CHECK=1 -e SKIP_EVAL=1 \
    "$CONTAINER_NAME" bash -lc "
      source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr && $*
    "
}

echo "=== Prerequisites inside container ==="
run_in_container "python scripts/check_prerequisites.py"

echo "=== Run pilot (SKIP_EVAL=1: agent only, L2) ==="
run_in_container "python scripts/run.py conf/deepseek-lite.conf -f"

echo "=== Verify L2 artifacts (cost.json, predictions, applicable_patch) ==="
run_in_container "python scripts/complete_l2_patch_selection.py --expr-dir experiment/deepseek-lite-pilot"
run_in_container "python scripts/verify_l2_output.py --expr-dir experiment/deepseek-lite-pilot --expected 10 --tasks-file conf/pilot_tasks.txt"

echo "=== Copy results to host pilot_output/ ==="
mkdir -p "$ROOT/pilot_output"
docker cp "$CONTAINER_NAME:/workspace/acr/experiment/deepseek-lite-pilot/." "$ROOT/pilot_output/"

echo "Done. Results in $ROOT/pilot_output/"
