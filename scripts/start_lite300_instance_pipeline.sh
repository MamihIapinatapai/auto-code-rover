#!/usr/bin/env bash
# Start per-instance Lite 300 pipeline (L2 verify → L3 → Feishu) in tmux or nohup.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SESSION="${TMUX_SESSION:-lite300-instances}"
USE_TMUX="${USE_TMUX:-1}"
LOG="${ROOT}/lite300_logs/instance_pipeline.log"

mkdir -p "${ROOT}/lite300_logs"

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi

python3 <<'PY' > "${ROOT}/lite300_logs/feishu_skip_instances.txt"
import json
from pathlib import Path
root = Path(".")
skip = set()
for repo in ("flask", "seaborn", "astropy", "requests", "pylint"):
    p = root / "lite300_output/repos" / repo / "eval_progress.json"
    if p.is_file():
        skip.update(json.loads(p.read_text())["done"])
print("\n".join(sorted(skip)))
PY

echo "Skip list: $(wc -l < "${ROOT}/lite300_logs/feishu_skip_instances.txt") instances (already L3)"

CMD="cd ${ROOT} && source conf/.env 2>/dev/null || true; python3 scripts/lite300_process_instances.py 2>&1 | tee -a ${LOG}"

if [[ "$USE_TMUX" == "1" ]] && command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "tmux session $SESSION already exists. Attach: tmux attach -t $SESSION"
    exit 0
  fi
  tmux new-session -d -s "$SESSION" "bash -lc $(printf '%q' "$CMD")"
  echo "Started tmux session: $SESSION"
  echo "  attach: tmux attach -t $SESSION"
  echo "  log:    tail -f $LOG"
else
  nohup bash -lc "$CMD" > "${ROOT}/lite300_logs/instance_pipeline.nohup.log" 2>&1 &
  echo "Started background PID $! (log: $LOG)"
fi
