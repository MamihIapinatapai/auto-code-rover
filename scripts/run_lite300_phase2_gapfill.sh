#!/usr/bin/env bash
# Phase2: rerun missing tasks per repo until verify passes or max rounds exhausted.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MAX_ROUNDS="${MAX_ROUNDS:-5}"
INCLUDE_BUCKETS="${INCLUDE_BUCKETS:-1}"

PHASE1_REPOS=(
  flask seaborn xarray astropy requests pylint
  sphinx pytest matplotlib scikit-learn sympy django
)

for round in $(seq 1 "$MAX_ROUNDS"); do
  echo "========== Phase2 round $round / $MAX_ROUNDS =========="
  any=0
  for repo in "${PHASE1_REPOS[@]}"; do
    if python3 scripts/list_lite300_missing.py --repo "$repo" | grep -q .; then
      any=1
      echo "--- gap-fill repo=$repo ---"
      extra=()
      if [[ "$INCLUDE_BUCKETS" -eq 1 ]]; then
        extra=(--include-failed-buckets)
      fi
      REPO="$repo" bash scripts/rerun_lite300_missing.sh "${extra[@]}" \
        2>&1 | tee -a "lite300_logs/${repo}_phase2_r${round}.log" || true
    fi
  done
  python3 scripts/lite300_status.py
  if [[ "$any" -eq 0 ]]; then
    echo "No missing instances across repos."
    break
  fi
done
