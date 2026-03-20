#!/usr/bin/env bash
set -euo pipefail

# Restart ingest summary rewrite run for a target index directory.
# Usage:
#   restart_rewrite_ingest_summaries_nohup.sh [target_dir] [ingest_pattern] [--no-clear-log]
#
# Defaults:
#   target_dir = current directory
#   when run from ./pdfs, defaults to ./pdfs/securitybooks

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR=""
INGEST_PATTERN=""
CLEAR_LOG=1

for arg in "$@"; do
  case "$arg" in
    --no-clear-log)
      CLEAR_LOG=0
      ;;
    -*)
      echo "[ERROR] Unknown flag: $arg" >&2
      exit 1
      ;;
    *)
      if [[ -z "$TARGET_DIR" ]]; then
        TARGET_DIR="$arg"
      elif [[ -z "$INGEST_PATTERN" ]]; then
        INGEST_PATTERN="$arg"
      else
        echo "[ERROR] Too many positional arguments. Usage: $0 [target_dir] [ingest_pattern] [--no-clear-log]" >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$TARGET_DIR" ]]; then
  if [[ "$(pwd)" == "$SCRIPT_DIR" && -d "$SCRIPT_DIR/securitybooks" ]]; then
    TARGET_DIR="$SCRIPT_DIR/securitybooks"
  else
    TARGET_DIR="$(pwd)"
  fi
fi

if [[ -z "$INGEST_PATTERN" ]]; then
  INGEST_PATTERN="*_semantic_ingest.json"
fi

if [[ "$TARGET_DIR" == "$SCRIPT_DIR" && -d "$SCRIPT_DIR/securitybooks" ]]; then
  TARGET_DIR="$SCRIPT_DIR/securitybooks"
fi

RUN_SCRIPT="$SCRIPT_DIR/run_rewrite_ingest_summaries.sh"
LOG_FILE="$TARGET_DIR/rewrite_ingest_summaries.log"
PID_FILE="$TARGET_DIR/.rewrite_ingest_summaries.pid"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[ERROR] Target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

if [[ ! -x "$RUN_SCRIPT" ]]; then
  echo "[ERROR] Missing executable run script: $RUN_SCRIPT" >&2
  exit 1
fi

echo "[INFO] Restart target: $TARGET_DIR"
echo "[INFO] Ingest pattern: $INGEST_PATTERN"
echo "[INFO] Looking for running summary rewrite processes..."
mapfile -t PIDS < <(
  pgrep -u "$USER" -f "/pdfs/rewrite_ingest_summaries.py|/pdfs/run_rewrite_ingest_summaries.sh|/pdfs/restart_rewrite_ingest_summaries_nohup.sh" || true
)

if [[ ${#PIDS[@]} -gt 0 ]]; then
  echo "[INFO] Stopping PIDs: ${PIDS[*]}"
  kill "${PIDS[@]}" || true
  sleep 2
  mapfile -t STILL_UP < <(
    pgrep -u "$USER" -f "/pdfs/rewrite_ingest_summaries.py|/pdfs/run_rewrite_ingest_summaries.sh|/pdfs/restart_rewrite_ingest_summaries_nohup.sh" || true
  )
  if [[ ${#STILL_UP[@]} -gt 0 ]]; then
    echo "[WARN] Forcing stop for PIDs: ${STILL_UP[*]}"
    kill -9 "${STILL_UP[@]}" || true
  fi
else
  echo "[INFO] No matching summary rewrite processes found."
fi

if [[ $CLEAR_LOG -eq 1 ]]; then
  : > "$LOG_FILE"
  echo "[INFO] Cleared log: $LOG_FILE"
else
  echo "[INFO] Keeping existing log: $LOG_FILE"
fi

cd "$TARGET_DIR"
echo "[INFO] Starting fresh nohup run..."
nohup env INDEX_DIR="$TARGET_DIR" INGEST_PATTERN="$INGEST_PATTERN" "$RUN_SCRIPT" > "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "[OK] Restarted summary rewrite."
echo "  PID: $NEW_PID"
echo "  PID file: $PID_FILE"
echo "  Log: $LOG_FILE"
echo "  Tail: tail -f \"$LOG_FILE\""
