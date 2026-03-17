#!/usr/bin/env bash
set -euo pipefail

# Restart stage-2 semantic batch for a target index directory.
# Usage:
#   restart_semantic_batch_nohup.sh [target_dir] [--no-clear-log]
#
# Defaults:
#   target_dir = current directory

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"
CLEAR_LOG=1

if [[ "${1:-}" == "--no-clear-log" ]]; then
  if [[ "$(pwd)" == "$SCRIPT_DIR" && -d "$SCRIPT_DIR/securitybooks" ]]; then
    TARGET_DIR="$SCRIPT_DIR/securitybooks"
  else
    TARGET_DIR="$(pwd)"
  fi
  CLEAR_LOG=0
elif [[ "${2:-}" == "--no-clear-log" ]]; then
  CLEAR_LOG=0
fi

if [[ "$TARGET_DIR" == "$SCRIPT_DIR" && -d "$SCRIPT_DIR/securitybooks" ]]; then
  TARGET_DIR="$SCRIPT_DIR/securitybooks"
fi

RUN_SCRIPT="$SCRIPT_DIR/run_semantic_batch.sh"
LOG_FILE="$TARGET_DIR/semantic_batch.log"
PID_FILE="$TARGET_DIR/.semantic_batch.pid"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[ERROR] Target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

if [[ ! -x "$RUN_SCRIPT" ]]; then
  echo "[ERROR] Missing executable run script: $RUN_SCRIPT" >&2
  exit 1
fi

echo "[INFO] Restart target: $TARGET_DIR"
echo "[INFO] Looking for running semantic batch processes..."
mapfile -t PIDS < <(
  pgrep -u "$USER" -f "/pdfs/batch_semantic_rechunk.py|/pdfs/semantic_rechunk_qwen3.py .*\\.semantic_work/.retry_state/|/pdfs/filter_non_book_content.py|/pdfs/improve_questions.py|/pdfs/improve_summaries.py" || true
)

if [[ ${#PIDS[@]} -gt 0 ]]; then
  echo "[INFO] Stopping PIDs: ${PIDS[*]}"
  kill "${PIDS[@]}" || true
  sleep 2
  mapfile -t STILL_UP < <(
    pgrep -u "$USER" -f "/pdfs/batch_semantic_rechunk.py|/pdfs/semantic_rechunk_qwen3.py .*\\.semantic_work/.retry_state/|/pdfs/filter_non_book_content.py|/pdfs/improve_questions.py|/pdfs/improve_summaries.py" || true
  )
  if [[ ${#STILL_UP[@]} -gt 0 ]]; then
    echo "[WARN] Forcing stop for PIDs: ${STILL_UP[*]}"
    kill -9 "${STILL_UP[@]}" || true
  fi
else
  echo "[INFO] No matching semantic batch processes found."
fi

if [[ $CLEAR_LOG -eq 1 ]]; then
  : > "$LOG_FILE"
  echo "[INFO] Cleared log: $LOG_FILE"
else
  echo "[INFO] Keeping existing log: $LOG_FILE"
fi

cd "$TARGET_DIR"
echo "[INFO] Starting fresh nohup run..."
nohup "$RUN_SCRIPT" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "[OK] Restarted."
echo "  PID: $NEW_PID"
echo "  PID file: $PID_FILE"
echo "  Log: $LOG_FILE"
echo "  Tail: tail -f \"$LOG_FILE\""
