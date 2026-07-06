#!/usr/bin/env bash
# Gate R0: ver1 base with ver1.1 mechanical pipeline disabled.
# Usage: ./scripts/start_spec_parser_ver1_probe.sh [instance_id]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ACR_SYMPY_PIPELINE_V2=0
export ACR_SEMANTIC_INJECTION_VER1=1
export PIPELINE_PROFILE=spec_parser_ver1

INSTANCE="${1:-sympy__sympy-12481}"
echo "Gate R0 smoke: profile=spec_parser_ver1 ACR_SYMPY_PIPELINE_V2=0 instance=${INSTANCE}"

python scripts/lite300_process_instances.py \
  --pipeline-profile spec_parser_ver1 \
  --task-list conf/lite300_tasks/sympy_five_probes.txt \
  --instance-id "$INSTANCE" \
  --max-instances 1 \
  2>&1 | tee "lite300_logs/profiles/spec_parser_ver1/gate_r0_smoke.log" || true

echo "Check: localization_artifact should have checklist_injected=false when v2 off"
echo "Check: semantic_injection_ver1.json should exist under output_*/"
