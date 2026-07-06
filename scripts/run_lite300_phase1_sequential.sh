#!/usr/bin/env bash
# Phase1: run L2+verify for each repo in ascending size order (no parallel repos).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

PHASE1_REPOS=(
  flask seaborn xarray astropy requests pylint
  sphinx pytest matplotlib scikit-learn sympy django
)

mkdir -p "$ROOT/lite300_logs"

for repo in "${PHASE1_REPOS[@]}"; do
  echo "========== Phase1 L2 repo=$repo =========="
  REPO="$repo" bash scripts/run_lite300_repo.sh --l2-only 2>&1 | tee -a "lite300_logs/${repo}_phase1.log"
  python3 scripts/lite300_status.py --repo "$repo"
done

echo "Phase1 sequential complete."
python3 scripts/lite300_status.py
