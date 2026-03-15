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
# Input selection is now driven by stage1_json_manifest.json from stage-1.
TARGET_DIR="${TARGET_DIR:-}"
if [[ -z "$TARGET_DIR" && "${1:-}" != "" && "${1:0:1}" != "-" ]]; then
  TARGET_DIR="$1"
  shift
fi

# Path-safe default:
# - If launched from shared scripts dir, default to the standard index dir.
# - Otherwise default to current directory.
if [[ -z "$TARGET_DIR" ]]; then
  if [[ "$(pwd)" == "$SCRIPT_DIR" && -d "$SCRIPT_DIR/securitybooks" ]]; then
    TARGET_DIR="$SCRIPT_DIR/securitybooks"
  else
    TARGET_DIR="$(pwd)"
  fi
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[ERROR] Target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

WORK_DIR="${WORK_DIR:-.semantic_work}"
STATUS_FILE="${STATUS_FILE:-semantic_batch_status.json}"
MAX_PASSES="${MAX_PASSES:-20}"

export PYTHONUNBUFFERED=1
export TARGET_DIR

cd "$TARGET_DIR"
exec "$PYTHON_BIN" "$SCRIPT_DIR/batch_semantic_rechunk.py" \
  --work-dir "$WORK_DIR" \
  --status-file "$STATUS_FILE" \
  --max-passes "$MAX_PASSES" \
  "$@"
