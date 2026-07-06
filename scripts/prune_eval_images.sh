#!/usr/bin/env bash
# Cleanup after incremental SWE-bench eval.
# Default: remove sweb.eval containers/images only; KEEP autocoderover/* preloaded testbeds.
# Legacy disk-saving mode: PRUNE_AUTOCODEROVER_IMAGES=1 (or run_eval_incremental.py --prune-preloaded-images)
set -euo pipefail

docker ps -a --filter "name=sweb.eval" -q | xargs -r docker rm -f 2>/dev/null || true

if [[ "${PRUNE_AUTOCODEROVER_IMAGES:-0}" == "1" ]]; then
  docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E 'sweb\.eval|autocoderover' \
    | xargs -r docker rmi -f 2>/dev/null || true
else
  docker images --format '{{.Repository}}:{{.Tag}}' \
    | grep -E '^sweb\.eval' \
    | xargs -r docker rmi -f 2>/dev/null || true
fi
