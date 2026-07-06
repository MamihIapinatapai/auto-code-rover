#!/usr/bin/env bash
# Shared constants for Lite 300 per-repo pipeline.
set -euo pipefail

LITE300_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Repo keys used in conf/lite300_tasks/<REPO>.txt and lite300_output/repos/<REPO>/
LITE300_REPOS=(
  django sympy matplotlib scikit-learn pytest sphinx
  astropy requests pylint xarray seaborn flask
)

lite300_expected_count() {
  local repo="$1"
  local f="${LITE300_ROOT}/conf/lite300_tasks/${repo}.txt"
  if [[ ! -f "$f" ]]; then
    echo "Missing task file: $f" >&2
    return 1
  fi
  grep -cve '^[[:space:]]*$' -e '^#' "$f"
}

lite300_expr_dir() {
  echo "experiment/deepseek-lite-300/repos/${1}"
}

lite300_sync_dir() {
  echo "lite300_output/repos/${1}"
}

lite300_num_processes() {
  case "$1" in
    django|sympy) echo 1 ;;
    *) echo 2 ;;
  esac
}

# Optional second arg: tasks file relative to repo root (default: conf/lite300_tasks/<repo>.txt)
lite300_generate_conf() {
  local repo="$1"
  local tasks_rel="${2:-conf/lite300_tasks/${repo}.txt}"
  local suffix=""
  if [[ "$tasks_rel" != "conf/lite300_tasks/${repo}.txt" ]]; then
    suffix="-missing"
  fi
  local out="${LITE300_ROOT}/conf/generated/deepseek-lite-300-${repo}${suffix}.conf"
  local nproc
  nproc="$(lite300_num_processes "$repo")"
  mkdir -p "${LITE300_ROOT}/conf/generated"
  sed -e "s/REPO_PLACEHOLDER/${repo}/g" \
      -e "s|TASKS_FILE_PLACEHOLDER|${tasks_rel}|g" \
      -e "s/num_processes:2/num_processes:${nproc}/" \
    "${LITE300_ROOT}/conf/deepseek-lite-300.repo.conf.template" > "$out"
  echo "$out"
}
