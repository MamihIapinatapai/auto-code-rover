#!/usr/bin/env bash
# Phase1: at most MAX_PARALLEL repos running L2 concurrently (default 2).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MAX_PARALLEL="${MAX_PARALLEL:-2}"

PHASE1_REPOS=(
  flask seaborn xarray astropy requests pylint
  sphinx pytest matplotlib scikit-learn sympy django
)

mkdir -p "$ROOT/lite300_logs"
LOCK="${ROOT}/lite300_logs/phase1.lock"
touch "$LOCK"
cleanup() { rm -f "$LOCK"; }
trap cleanup EXIT

running=0
pids=()

wait_slot() {
  while [[ "$running" -ge "$MAX_PARALLEL" ]]; do
    for i in "${!pids[@]}"; do
      if ! kill -0 "${pids[$i]}" 2>/dev/null; then
        wait "${pids[$i]}" || true
        unset 'pids[i]'
        running=$((running - 1))
      fi
    done
    pids=("${pids[@]}")
    sleep 5
  done
}

for repo in "${PHASE1_REPOS[@]}"; do
  wait_slot
  echo "Starting L2 repo=$repo (running=$running)"
  (
    REPO="$repo" bash scripts/run_lite300_repo.sh --l2-only \
      2>&1 | tee "lite300_logs/${repo}_phase1.log"
  ) &
  pids+=("$!")
  running=$((running + 1))
done

for pid in "${pids[@]}"; do
  wait "$pid" || true
done

python3 scripts/lite300_status.py
echo "Phase1 stagger complete (MAX_PARALLEL=$MAX_PARALLEL)."
