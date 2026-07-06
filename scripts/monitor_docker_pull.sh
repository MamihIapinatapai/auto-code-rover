#!/usr/bin/env bash
# Monitor docker pull progress (uses existing daemon registry-mirrors)
LOG="${1:-/datadisk/pengxm/auto-code-rover/docker_pull.log}"
IMAGE="yuntongzhang/auto-code-rover:experiment"
echo "=== Registry mirrors (daemon.json) ==="
python3 -c "import json; print(json.load(open('/etc/docker/daemon.json')).get('registry-mirrors',[]))" 2>/dev/null || true
echo "=== Image status ==="
docker images "$IMAGE" --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}' 2>/dev/null || true
if pgrep -f "docker pull.*auto-code-rover" >/dev/null; then
  echo "=== Pull in progress (last 8 log lines) ==="
  tail -8 "$LOG" 2>/dev/null || true
else
  echo "=== No active pull process ==="
  tail -5 "$LOG" 2>/dev/null || true
fi
