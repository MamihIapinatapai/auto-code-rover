#!/usr/bin/env bash
# Wait for Phase1 lock, then run Phase2 gap-fill and Phase3 L3+Feishu.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCK="${ROOT}/lite300_logs/phase1.lock"
LOG="${ROOT}/lite300_logs/phase23_followup.log"

mkdir -p "${ROOT}/lite300_logs"

{
  echo "=== $(date -Is) waiting for Phase1 (lock=$LOCK) ==="
  while [[ -f "$LOCK" ]]; do
    sleep 60
  done
  echo "=== $(date -Is) Phase1 done, starting Phase2 ==="
  bash scripts/run_lite300_phase2_gapfill.sh
  echo "=== $(date -Is) Phase2 done, starting Phase3 ==="
  bash scripts/run_lite300_phase3_l3_feishu.sh
  echo "=== $(date -Is) Phase2+3 followup complete ==="
} 2>&1 | tee -a "$LOG"
