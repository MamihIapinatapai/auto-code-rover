#!/usr/bin/env bash
# Clone DeepSWE benchmark and generate task index files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEEPSWE_ROOT="${DEEPSWE_ROOT:-$ROOT/third_party/deep-swe}"
FROM_HF=false

usage() {
  echo "Usage: $0 [--from-hf]"
  echo "  --from-hf   Download from Hugging Face (requires HF_TOKEN in conf/.env)"
  echo "Env: DEEPSWE_ROOT (default: \$ROOT/third_party/deep-swe)"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from-hf) FROM_HF=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
done

if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
  echo "Loaded $ROOT/conf/.env"
fi

if [[ "$FROM_HF" == true ]]; then
  echo "Downloading datacurve/deep-swe from Hugging Face to $DEEPSWE_ROOT ..."
  python3 - <<PY
import os
from pathlib import Path

try:
    from huggingface_hub import snapshot_download
except ImportError as e:
    raise SystemExit("Install huggingface_hub: pip install huggingface_hub") from e

dest = Path("${DEEPSWE_ROOT}")
dest.mkdir(parents=True, exist_ok=True)
token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
snapshot_download(
    "datacurve/deep-swe",
    repo_type="dataset",
    local_dir=str(dest),
    token=token,
)
print(f"Downloaded to {dest}")
PY
else
  if [[ -d "$DEEPSWE_ROOT/.git" ]]; then
    echo "DeepSWE already cloned at $DEEPSWE_ROOT (skipping git clone)"
  else
    echo "Cloning datacurve-ai/deep-swe to $DEEPSWE_ROOT ..."
    git clone --depth 1 https://github.com/datacurve-ai/deep-swe.git "$DEEPSWE_ROOT"
  fi
fi

TASKS_DIR="$DEEPSWE_ROOT/tasks"
if [[ ! -d "$TASKS_DIR" ]]; then
  echo "ERROR: tasks directory not found at $TASKS_DIR" >&2
  exit 1
fi

python3 "$ROOT/scripts/deepswe_index_tasks.py" "$TASKS_DIR" "$ROOT/conf"
echo "DeepSWE setup complete."
