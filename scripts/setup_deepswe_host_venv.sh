#!/usr/bin/env bash
# Create a local venv with deps to run DeepSWE scripts on the host (outside Docker).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-deepswe"
python3 -m venv "$VENV"
"$VENV/bin/pip" install -U pip
"$VENV/bin/pip" install -r "$ROOT/requirements-deepswe-host.txt"
echo "Host venv ready: source $VENV/bin/activate"
