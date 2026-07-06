#!/usr/bin/env bash
# Start tmux session for Lite 300 Baseline300 full pipeline (staggered L2, not 12-way parallel).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSION="${LITE300_TMUX_SESSION:-lite300-baseline}"
mkdir -p "$ROOT/lite300_logs"

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Tmux session '$SESSION' already exists."
  echo "  attach: tmux attach -t $SESSION"
  exit 0
fi

PIPELINE_CMD="cd $ROOT && source scripts/source_env.sh && bash scripts/run_lite300_baseline_all.sh 2>&1 | tee -a lite300_logs/baseline_all.log"
STATUS_CMD="cd $ROOT && watch -n 120 python3 scripts/lite300_status.py"

tmux new-session -d -s "$SESSION" -n pipeline bash -lc "$PIPELINE_CMD"
tmux new-window -t "$SESSION" -n status bash -lc "$STATUS_CMD"

echo "Started tmux session '$SESSION' (pipeline + status windows)."
echo "  attach: tmux attach -t $SESSION"
echo "  logs:   $ROOT/lite300_logs/baseline_all.log"
