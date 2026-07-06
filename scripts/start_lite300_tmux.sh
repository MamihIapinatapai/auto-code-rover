#!/usr/bin/env bash
# Start tmux session lite300-baseline with one window per repo.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=scripts/lite300_common.sh
source "$ROOT/scripts/lite300_common.sh"

SESSION="${LITE300_TMUX_SESSION:-lite300-baseline}"
mkdir -p "$ROOT/lite300_logs"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Tmux session '$SESSION' already exists."
  echo "  attach: tmux attach -t $SESSION"
  exit 0
fi

first=1
for repo in "${LITE300_REPOS[@]}"; do
  cmd="cd $ROOT && source scripts/source_env.sh && REPO=$repo bash scripts/run_lite300_repo.sh 2>&1 | tee lite300_logs/${repo}_pipeline.log"
  if [[ "$first" -eq 1 ]]; then
    tmux new-session -d -s "$SESSION" -n "$repo" bash -lc "$cmd"
    first=0
  else
    tmux new-window -t "$SESSION" -n "$repo" bash -lc "$cmd"
  fi
done

echo "Started tmux session '$SESSION' with ${#LITE300_REPOS[@]} windows."
echo "  attach: tmux attach -t $SESSION"
echo "  logs:   $ROOT/lite300_logs/"
