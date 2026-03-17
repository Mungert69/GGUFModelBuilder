#!/usr/bin/env bash
set -euo pipefail

# Stage-5 convenience runner:
# - Uses resume/checkpoint by default
# - Non-destructive by default (writes *_semantic_ingest_resplit.json)
# - Unbuffered logging with tee
#
# Usage:
#   ./run_stage5_resplit_all.sh
#
# Optional env overrides:
#   INDEX_DIR=/abs/path/to/securitybooks
#   PATTERN="*_semantic_ingest.json"
#   MAX_OUTPUT_TOKENS=4096
#   MAX_WINDOW=24
#   MAX_FILES=0
#   IN_PLACE=0
#   NO_RESUME=0
#   DRY_RUN=0
#   CONFIG_PATH=""
#   LOG_DIR=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

INDEX_DIR="${INDEX_DIR:-$SCRIPT_DIR/securitybooks}"
PATTERN="${PATTERN:-*_semantic_ingest.json}"
MAX_OUTPUT_TOKENS="${MAX_OUTPUT_TOKENS:-4096}"
MAX_WINDOW="${MAX_WINDOW:-24}"
MAX_FILES="${MAX_FILES:-0}"
IN_PLACE="${IN_PLACE:-0}"
NO_RESUME="${NO_RESUME:-0}"
DRY_RUN="${DRY_RUN:-0}"
CONFIG_PATH="${CONFIG_PATH:-}"
LOG_DIR="${LOG_DIR:-$INDEX_DIR}"

mkdir -p "$LOG_DIR"
TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="$LOG_DIR/stage5_resplit_run_${TS}.log"
SUMMARY_JSON="$LOG_DIR/stage5_resplit_summary_${TS}.json"

# Use project venv Python directly (no `. act` required).
cd "$PROJECT_DIR"
PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
    echo "[WARN] venv python not found at $PROJECT_DIR/venv/bin/python; falling back to $PYTHON_BIN"
  else
    echo "[ERROR] No Python interpreter found." >&2
    exit 1
  fi
fi

CMD=(
  "$PYTHON_BIN" -u "$SCRIPT_DIR/stage5_resplit_oversize_ingest.py"
  --index-dir "$INDEX_DIR"
  --pattern "$PATTERN"
  --max-output-tokens "$MAX_OUTPUT_TOKENS"
  --max-window "$MAX_WINDOW"
  --summary-file "$SUMMARY_JSON"
)

if [[ "$MAX_FILES" != "0" ]]; then
  CMD+=(--max-files "$MAX_FILES")
fi
if [[ "$IN_PLACE" == "1" ]]; then
  CMD+=(--in-place)
fi
if [[ "$NO_RESUME" == "1" ]]; then
  CMD+=(--no-resume)
fi
if [[ "$DRY_RUN" == "1" ]]; then
  CMD+=(--dry-run)
fi
if [[ -n "$CONFIG_PATH" ]]; then
  CMD+=(--config "$CONFIG_PATH")
fi

echo "[INFO] Stage-5 wrapper starting at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[INFO] index_dir=$INDEX_DIR pattern=$PATTERN"
echo "[INFO] token_cap=$MAX_OUTPUT_TOKENS max_window=$MAX_WINDOW max_files=$MAX_FILES"
echo "[INFO] in_place=$IN_PLACE no_resume=$NO_RESUME dry_run=$DRY_RUN"
echo "[INFO] summary_json=$SUMMARY_JSON"
echo "[INFO] run_log=$RUN_LOG"
echo "[INFO] command: ${CMD[*]}"

PYTHONUNBUFFERED=1 "${CMD[@]}" 2>&1 | tee "$RUN_LOG"

echo "[DONE] Stage-5 wrapper finished."
echo "[DONE] Summary: $SUMMARY_JSON"
echo "[DONE] Log: $RUN_LOG"
