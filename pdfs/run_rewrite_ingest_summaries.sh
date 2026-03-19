#!/usr/bin/env bash
set -euo pipefail

# Run ingest summary rewrite pass with sensible defaults.
# Environment overrides:
#   INDEX_DIR, INGEST_PATTERN, STATUS_FILE, SUMMARY_TOKEN_CAP, MAX_FILES, MAX_ROWS_PER_FILE, DRY_RUN

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON_BIN="$REPO_DIR/venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

INDEX_DIR="${INDEX_DIR:-$SCRIPT_DIR/securitybooks}"
INGEST_PATTERN="${INGEST_PATTERN:-*_semantic_ingest.json}"
STATUS_FILE="${STATUS_FILE:-$INDEX_DIR/.rewrite_ingest_summaries_status.json}"
SUMMARY_TOKEN_CAP="${SUMMARY_TOKEN_CAP:-4096}"
MAX_FILES="${MAX_FILES:-0}"
MAX_ROWS_PER_FILE="${MAX_ROWS_PER_FILE:-0}"
DRY_RUN="${DRY_RUN:-0}"

ARGS=(
  "$SCRIPT_DIR/rewrite_ingest_summaries.py"
  --index-dir "$INDEX_DIR"
  --pattern "$INGEST_PATTERN"
  --status-file "$STATUS_FILE"
  --summary-token-cap "$SUMMARY_TOKEN_CAP"
)

if [[ "$MAX_FILES" != "0" ]]; then
  ARGS+=(--max-files "$MAX_FILES")
fi
if [[ "$MAX_ROWS_PER_FILE" != "0" ]]; then
  ARGS+=(--max-rows-per-file "$MAX_ROWS_PER_FILE")
fi
if [[ "$DRY_RUN" == "1" ]]; then
  ARGS+=(--dry-run)
fi

echo "[INFO] python: $PYTHON_BIN"
echo "[INFO] index_dir: $INDEX_DIR"
echo "[INFO] pattern: $INGEST_PATTERN"
echo "[INFO] status_file: $STATUS_FILE"
echo "[INFO] summary_token_cap: $SUMMARY_TOKEN_CAP"
echo "[INFO] max_files: $MAX_FILES"
echo "[INFO] max_rows_per_file: $MAX_ROWS_PER_FILE"
echo "[INFO] dry_run: $DRY_RUN"
echo "[INFO] cmd: $PYTHON_BIN ${ARGS[*]}"

exec "$PYTHON_BIN" -u "${ARGS[@]}"

