#!/usr/bin/env bash
# Full Baseline300 pipeline: Phase1 stagger → Phase2 gap-fill → Phase3 L3+Feishu.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source scripts/source_env.sh

mkdir -p lite300_logs
LOG="lite300_logs/baseline_all.log"

{
  echo "=== $(date -Is) Baseline300 start ==="
  bash scripts/run_lite300_phase1_stagger.sh
  bash scripts/run_lite300_phase2_gapfill.sh
  bash scripts/run_lite300_phase3_l3_feishu.sh
  echo "=== $(date -Is) Baseline300 done ==="
} 2>&1 | tee -a "$LOG"
