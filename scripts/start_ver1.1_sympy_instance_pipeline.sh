#!/usr/bin/env bash
# Start SymPy ver1.1 per-instance pipeline (L2 verify/rerun → L3 → Feishu) in tmux.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSION="${TMUX_SESSION:-ver1_1-sympy-instances}"
USE_TMUX="${USE_TMUX:-1}"
PROFILE="ver1.1"
LOG="${ROOT}/lite300_logs/profiles/${PROFILE}/instance_pipeline.log"
INSTANCES_FILE="${INSTANCES_FILE:-conf/lite300_tasks/sympy.txt}"
RESET_TERMINAL="${RESET_TERMINAL:-1}"

mkdir -p "${ROOT}/lite300_logs/profiles/${PROFILE}"
# L3 docker cp writes to SYNC_DIR on host — must be owned by the runner (not root via docker exec).
mkdir -p "${ROOT}/lite300_output_ver1.1/repos/sympy"

CONTAINER="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  docker exec "$CONTAINER" bash -lc \
    "mkdir -p /workspace/acr/experiment/deepseek-lite-300-ver1.1/repos/sympy && \
     chown -R ${HOST_UID}:${HOST_GID} /workspace/acr/experiment/deepseek-lite-300-ver1.1 /workspace/acr/lite300_output_ver1.1"
else
  mkdir -p "${ROOT}/experiment/deepseek-lite-300-ver1.1/repos/sympy" 2>/dev/null || true
fi

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "ERROR: DEEPSEEK_API_KEY not set (source conf/.env)"
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"; then
  echo "ERROR: Docker container not running. Start with: bash scripts/run_pilot_docker.sh"
  exit 1
fi

TERMINAL_FILE="${ROOT}/lite300_logs/profiles/${PROFILE}/instance_pipeline_terminal.json"
RETRY_FILE="${ROOT}/lite300_logs/profiles/${PROFILE}/l2_retry_state.json"

if [[ "$RESET_TERMINAL" == "1" ]]; then
  echo "[]" > "$TERMINAL_FILE"
  echo "{}" > "$RETRY_FILE"
  echo "Reset ver1.1 terminal + retry state for full run"
fi

CMD="cd ${ROOT} && set -a && source conf/.env && set +a && \
export PIPELINE_PROFILE=${PROFILE} SYSTEM_VERSION=ver1.1 && \
python3 scripts/lite300_process_instances.py \
  --instances-file ${INSTANCES_FILE} \
  --system-version ver1.1 \
  --pipeline-profile ${PROFILE} \
  --reset-retry \
  2>&1 | tee -a ${LOG}"

echo "SymPy ver1.1 per-instance pipeline"
echo "  profile=${PROFILE} instances=${INSTANCES_FILE}"
echo "  log=${LOG}"
echo "  L2: verify + rerun (max 3) | L3: single-instance | Feishu: per instance"

if [[ "$USE_TMUX" == "1" ]] && command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session $SESSION already exists."
    echo "  attach: tmux attach -t $SESSION"
    echo "  kill:   tmux kill-session -t $SESSION  # then re-run this script"
    exit 0
  fi
  tmux new-session -d -s "$SESSION" "bash -lc $(printf '%q' "$CMD")"
  echo "Started tmux session: $SESSION"
  echo "  attach: tmux attach -t $SESSION"
  echo "  log:    tail -f ${LOG}"
else
  nohup bash -lc "$CMD" > "${ROOT}/lite300_logs/profiles/${PROFILE}/instance_pipeline.nohup.log" 2>&1 &
  echo "Started background PID $! (log: ${LOG})"
fi
