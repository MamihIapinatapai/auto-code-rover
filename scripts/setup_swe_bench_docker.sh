#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TARGET="/opt/SWE-bench-docker"
if [[ -d "$TARGET" && -f "$TARGET/run_evaluation.py" ]]; then
  echo "SWE-bench-docker already at $TARGET"
  exit 0
fi

if [[ ! -d "$ROOT/SWE-bench-docker/.git" ]]; then
  echo "Initializing SWE-bench-docker submodule..."
  git config --global --add safe.directory "$ROOT" 2>/dev/null || true
  git config --global --add safe.directory "$ROOT/SWE-bench-docker" 2>/dev/null || true
  git submodule update --init --recursive SWE-bench-docker
fi

echo "Installing SWE-bench-docker to $TARGET ..."
mkdir -p "$(dirname "$TARGET")"
rm -rf "$TARGET"
cp -a "$ROOT/SWE-bench-docker" "$TARGET"
chmod -R a+rX "$TARGET"

if [[ -f "$TARGET/requirements.txt" ]]; then
  source /root/miniconda3/etc/profile.d/conda.sh
  conda activate auto-code-rover
  pip install -q -r "$TARGET/requirements.txt"
fi
echo "SWE-bench-docker ready at $TARGET"
