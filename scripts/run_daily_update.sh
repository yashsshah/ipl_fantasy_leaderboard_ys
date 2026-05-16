#!/bin/zsh

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

cd "$REPO_ROOT"

mkdir -p "$REPO_ROOT/logs"

"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/scripts/daily_update_and_merge.py" "$@"