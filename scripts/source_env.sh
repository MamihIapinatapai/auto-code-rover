#!/usr/bin/env bash
# Load replication env from conf/.env (gitignored). Safe to source: no echo of secrets.
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  _SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
else
  _SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
fi
ROOT="$(cd "$_SCRIPT_DIR/.." && pwd)"
if [[ -f "$ROOT/conf/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "$ROOT/conf/.env"
  set +a
  echo "Loaded $ROOT/conf/.env"
else
  echo "No $ROOT/conf/.env — use: cp conf/.env.example conf/.env"
  return 1 2>/dev/null || exit 1
fi
export ACR_TOKEN_LIMIT="${ACR_TOKEN_LIMIT:-4096}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
