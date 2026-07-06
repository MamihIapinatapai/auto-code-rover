#!/usr/bin/env bash
# Upload Lite 300 eval results to Feishu Bitable.
# REPO=all uploads merged lite300_output/; REPO=<name> uploads single repo dir.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

REPO="${REPO:-all}"
SYSTEM_VERSION="${SYSTEM_VERSION:-Baseline}"
DRY_RUN="${DRY_RUN:-0}"
INSTANCE_ID="${INSTANCE_ID:-}"
L2_FAILURE="${L2_FAILURE:-}"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi

PYTHON="${ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

UPLOAD="${ROOT}/scripts/upload_results.py"
DRY_FLAG=""
INSTANCE_ARGS=()
if [[ "$DRY_RUN" == "1" ]]; then
  DRY_FLAG="--dry-run"
fi
if [[ -n "$INSTANCE_ID" ]]; then
  INSTANCE_ARGS+=(--instance-id "$INSTANCE_ID")
fi
if [[ -n "$L2_FAILURE" ]]; then
  UPLOAD_ARGS=(--system_version "$SYSTEM_VERSION" --l2-failure "$L2_FAILURE" $DRY_FLAG)
  if [[ "$REPO" != "all" ]]; then
    UPLOAD_ARGS+=(--expr-root "${ROOT}/$(lite300_expr_dir "$REPO")")
  fi
  echo "Upload L2 failure system_version=$SYSTEM_VERSION l2_failure=$L2_FAILURE dry_run=$DRY_RUN"
  "$PYTHON" "$UPLOAD" "${UPLOAD_ARGS[@]}"
  exit $?
fi

if [[ "$REPO" == "all" ]]; then
  LOG_PATH="${ROOT}/lite300_output"
else
  if [[ ! " ${LITE300_REPOS[*]} " =~ " ${REPO} " ]]; then
    echo "Unknown REPO: $REPO (use 'all' or one of: ${LITE300_REPOS[*]})"
    exit 1
  fi
  LOG_PATH="${ROOT}/$(lite300_sync_dir "$REPO")"
fi

if [[ ! -d "$LOG_PATH" ]]; then
  echo "Missing log_path directory: $LOG_PATH"
  exit 1
fi

echo "Upload system_version=$SYSTEM_VERSION log_path=$LOG_PATH dry_run=$DRY_RUN"
"$PYTHON" "$UPLOAD" \
  --system_version "$SYSTEM_VERSION" \
  --log_path "$LOG_PATH" \
  "${INSTANCE_ARGS[@]+"${INSTANCE_ARGS[@]}"}" \
  $DRY_FLAG
