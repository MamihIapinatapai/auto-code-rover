#!/usr/bin/env bash
# Phase3 v3: per-instance L2 verify → L3 → Feishu (no whole-repo verify gate).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p lite300_logs

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
fi

bash scripts/start_lite300_instance_pipeline.sh

echo "=== Monitor: python3 scripts/lite300_status.py ==="
echo "=== Log: tail -f lite300_logs/instance_pipeline.log ==="
