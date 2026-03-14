#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${VENV_PYTHON:-$PROJECT_DIR/venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python not found or not executable: $PYTHON_BIN" >&2
  echo "Set VENV_PYTHON to your interpreter path." >&2
  exit 1
fi

# Defaults for stage-2 semantic batch processing.
PATTERN="${PATTERN:-*_chunks.json}"
WORK_DIR="${WORK_DIR:-.semantic_work}"
STATUS_FILE="${STATUS_FILE:-semantic_batch_status.json}"
MAX_PASSES="${MAX_PASSES:-20}"

export PYTHONUNBUFFERED=1

exec "$PYTHON_BIN" "$SCRIPT_DIR/batch_semantic_rechunk.py" \
  --pattern "$PATTERN" \
  --work-dir "$WORK_DIR" \
  --status-file "$STATUS_FILE" \
  --max-passes "$MAX_PASSES" \
  "$@"

