#!/usr/bin/env bash
# Repair ver1.1 L3 sync (permission denied) and Feishu upload for instances that
# completed SWE-bench eval in experiment/ but failed docker cp to lite300_output_ver1.1.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER="${ACR_CONTAINER_NAME:-pengxm-acr-replicate}"
EXPR_DIR="experiment/deepseek-lite-300-ver1.1/repos/sympy"
SYNC_DIR="lite300_output_ver1.1/repos/sympy"
SYSTEM_VERSION="ver1.1"
PROFILE="ver1.1"

# Instances that finished L3 in experiment/ but sync/Feishu failed (exit 1).
L3_DONE_INSTANCES=(
  sympy__sympy-11400
  sympy__sympy-11870
  sympy__sympy-12171
  sympy__sympy-12236
  sympy__sympy-12454
  sympy__sympy-12481
  sympy__sympy-13031
)

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: Docker container $CONTAINER not running"
  exit 1
fi

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

echo "=== Step 1: Fix ownership (host uid=$HOST_UID gid=$HOST_GID) ==="
mkdir -p "$ROOT/$SYNC_DIR"
docker exec "$CONTAINER" bash -lc \
  "mkdir -p /workspace/acr/${EXPR_DIR} /workspace/acr/${SYNC_DIR} && \
   chown -R ${HOST_UID}:${HOST_GID} /workspace/acr/experiment/deepseek-lite-300-ver1.1 /workspace/acr/lite300_output_ver1.1"

echo "=== Step 2: Sync experiment → lite300_output_ver1.1 ==="
docker cp "$CONTAINER:/workspace/acr/${EXPR_DIR}/." "$ROOT/$SYNC_DIR/"
echo "Synced to $ROOT/$SYNC_DIR/"

if [[ ! -f "$ROOT/$SYNC_DIR/report/report.json" ]]; then
  echo "ERROR: report.json missing after sync"
  exit 1
fi

echo "=== Step 3: Feishu upsert for ${#L3_DONE_INSTANCES[@]} L3 instances ==="
for iid in "${L3_DONE_INSTANCES[@]}"; do
  echo "--- upload $iid ---"
  python3 scripts/upload_results.py \
    --system_version "$SYSTEM_VERSION" \
    --log_path "$ROOT/$SYNC_DIR" \
    --instance-id "$iid"
done

echo "=== Step 4: Mark instances in terminal state ==="
PROFILE="$PROFILE" ADD_IDS="$(printf '%s\n' "${L3_DONE_INSTANCES[@]}")" python3 <<'PY'
import json
import os
from pathlib import Path

profile = os.environ.get("PROFILE", "ver1.1")
add_ids = [ln.strip() for ln in os.environ.get("ADD_IDS", "").splitlines() if ln.strip()]
terminal_path = Path(f"lite300_logs/profiles/{profile}/instance_pipeline_terminal.json")
existing = json.loads(terminal_path.read_text()) if terminal_path.is_file() else []
merged = sorted(set(existing) | set(add_ids))
terminal_path.parent.mkdir(parents=True, exist_ok=True)
terminal_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
print(f"terminal: {len(existing)} -> {len(merged)} instances")
PY

echo "=== Done: sync + Feishu for ver1.1 L3 repair ==="
