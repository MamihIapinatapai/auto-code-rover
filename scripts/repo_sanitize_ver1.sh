#!/usr/bin/env bash
# TODO (ver1): aggressive git cleanup before L2/L3 eval to prevent patch pollution
set -euo pipefail

COMMIT="${1:-HEAD}"
REPO_PATH="${2:-.}"

cd "$REPO_PATH"
git reset --hard "$COMMIT"
git clean -fdx
