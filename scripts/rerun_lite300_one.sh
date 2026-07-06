#!/usr/bin/env bash
# Rerun L2 agent for a single Lite 300 instance (repair + per-instance verify).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

FOR_PIPELINE=0
INSTANCE_ID=""

for arg in "$@"; do
  case "$arg" in
    --for-pipeline) FOR_PIPELINE=1 ;;
    --*) echo "Unknown argument: $arg" >&2; exit 1 ;;
    *)
      if [[ -z "$INSTANCE_ID" ]]; then
        INSTANCE_ID="$arg"
      else
        echo "Usage: bash scripts/rerun_lite300_one.sh [--for-pipeline] <instance_id>" >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$INSTANCE_ID" ]]; then
  echo "Usage: bash scripts/rerun_lite300_one.sh [--for-pipeline] <instance_id>" >&2
  exit 1
fi

read -r REPO EXPR_DIR CONF_IN_CONTAINER VER1_FLAG <<<"$(python3 - <<PY
import os
import sys
sys.path.insert(0, "${ROOT}/scripts")
from lite300_instance_utils import (
    conf_file_for_repo,
    relative_expr_dir,
    repo_from_instance_id,
    resolve_pipeline_profile,
)
profile = resolve_pipeline_profile(os.environ.get("PIPELINE_PROFILE") or None)
repo = repo_from_instance_id("${INSTANCE_ID}")
if not repo:
    sys.exit(1)
expr = relative_expr_dir(repo, profile)
conf = conf_file_for_repo(repo, profile)
if conf.name.startswith("deepseek-lite-300-ver1"):
    conf_in = f"/workspace/acr/conf/{conf.name}"
else:
    conf_in = f"/workspace/acr/conf/generated/deepseek-lite-300-{repo}.conf"
ver1 = "1" if profile.name in ("ver1", "ver1.1") else "0"
print(repo, expr, conf_in, ver1)
PY
)" || {
  echo "Unknown repo for instance: $INSTANCE_ID"
  exit 1
}

CONTAINER_NAME="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
CONDA_SH="/root/miniconda3/etc/profile.d/conda.sh"
TASKS_ONE="lite300_logs/tasks_one_${INSTANCE_ID}.txt"
mkdir -p "${ROOT}/lite300_logs"
printf '%s\n' "$INSTANCE_ID" > "$TASKS_ONE"

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
  echo "Container $CONTAINER_NAME not running"
  exit 1
fi

PIPELINE_PROFILE="${PIPELINE_PROFILE:-baseline}"
echo "=== Rerun L2 instance=$INSTANCE_ID repo=$REPO profile=$PIPELINE_PROFILE EXPR_DIR=$EXPR_DIR (for_pipeline=$FOR_PIPELINE) ==="

DOCKER_ENV=( -e DEEPSEEK_API_KEY -e ACR_TOKEN_LIMIT -e ACR_SKIP_DOCKER_CHECK=1 -e SKIP_EVAL=1 )
if [[ "$VER1_FLAG" == "1" ]]; then
  DOCKER_ENV+=( -e ACR_SEMANTIC_INJECTION_VER1=1 )
fi

VER1_CLI=""
if [[ "$VER1_FLAG" == "1" ]]; then
  VER1_CLI="--enable-semantic-injection-ver1"
fi

docker exec "${DOCKER_ENV[@]}" "$CONTAINER_NAME" bash -lc "
  source $CONDA_SH && conda activate auto-code-rover && cd /workspace/acr &&
  cp /workspace/acr/${TASKS_ONE} /workspace/acr/${EXPR_DIR}/tasks_one_${INSTANCE_ID}.txt &&
  if [[ -d /workspace/acr/${EXPR_DIR} ]] && ls /workspace/acr/${EXPR_DIR}/applicable_patch >/dev/null 2>&1; then
    PYTHONPATH=/workspace/acr python app/main.py swe-bench --reproduce-and-review \
      --setup-map /opt/SWE-bench/setup_result/setup_map.json \
      --tasks-map /opt/SWE-bench/setup_result/tasks_map.json \
      --output-dir /workspace/acr/${EXPR_DIR} \
      --task-list-file /workspace/acr/${EXPR_DIR}/tasks_one_${INSTANCE_ID}.txt \
      --model litellm-generic-deepseek/deepseek-chat \
      --model-temperature 0.2 \
      --conv-round-limit 10 \
      --num-processes 1 \
      ${VER1_CLI} \
      --no-print
  else
    python scripts/run.py ${CONF_IN_CONTAINER} -f
  fi &&
  python scripts/complete_l2_patch_selection.py --expr-dir ${EXPR_DIR}
"

if [[ "$FOR_PIPELINE" -eq 1 ]]; then
  echo "=== Pipeline mode: skipping final verify (orchestrator will re-verify) ==="
  exit 0
fi

python3 scripts/verify_l2_instance.py --instance-id "$INSTANCE_ID" --pipeline-profile "$PIPELINE_PROFILE"
