#!/usr/bin/env bash
# Wait for experiment image, then run L2 pilot (logs to pilot_docker_run.log)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
IMAGE="yuntongzhang/auto-code-rover:experiment"
LOG="$ROOT/docker_pull.log"

echo "[$(date -Iseconds)] Waiting for $IMAGE ..."
while ! docker image inspect "$IMAGE" &>/dev/null; do
  if ! pgrep -f "docker pull.*auto-code-rover:experiment" >/dev/null; then
    echo "[$(date -Iseconds)] Pull not running; restarting..."
    docker pull "$IMAGE" >>"$LOG" 2>&1 &
  fi
  "$ROOT/scripts/monitor_docker_pull.sh" | tail -6
  sleep 120
done

echo "[$(date -Iseconds)] Image ready: $(docker images "$IMAGE" --format '{{.Size}}')"
bash "$ROOT/scripts/run_pilot_docker.sh" 2>&1 | tee "$ROOT/pilot_docker_run.log"
echo "[$(date -Iseconds)] L2 finished. See pilot_output/"

echo "[$(date -Iseconds)] Starting L3 incremental eval..."
bash "$ROOT/scripts/run_pilot_eval_incremental.sh" 2>&1 | tee "$ROOT/pilot_eval.log"
echo "[$(date -Iseconds)] L3 finished. See pilot_output/report/"
