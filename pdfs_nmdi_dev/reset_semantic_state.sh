#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$(pwd)}"
WORK_DIR_NAME="${WORK_DIR_NAME:-.semantic_work}"
STATUS_FILE_NAME="${STATUS_FILE_NAME:-semantic_batch_status.json}"
FORCE="${FORCE:-0}"

usage() {
  cat <<'EOF'
Usage:
  reset_semantic_state.sh [target_dir] [--force]

Behavior:
  - Removes semantic batch state for resumable runs:
    - <target_dir>/.semantic_work/
    - <target_dir>/semantic_batch_status.json
  - Also removes in-place work files:
    - <target_dir>/*_semantic_work.json

Options:
  --force   Also remove generated semantic outputs:
            - <target_dir>/*_out_*.json
            - <target_dir>/*_??????????????.json  (timestamped semantic block files)
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${2:-}" == "--force" || "${1:-}" == "--force" ]]; then
  FORCE=1
fi

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "[ERROR] Target directory does not exist: $TARGET_DIR" >&2
  exit 1
fi

echo "[INFO] Reset target: $TARGET_DIR"

WORK_DIR="$TARGET_DIR/$WORK_DIR_NAME"
STATUS_FILE="$TARGET_DIR/$STATUS_FILE_NAME"

if [[ -d "$WORK_DIR" ]]; then
  rm -rf "$WORK_DIR"
  echo "[OK] Removed $WORK_DIR"
else
  echo "[SKIP] No work dir: $WORK_DIR"
fi

if [[ -f "$STATUS_FILE" ]]; then
  rm -f "$STATUS_FILE"
  echo "[OK] Removed $STATUS_FILE"
else
  echo "[SKIP] No status file: $STATUS_FILE"
fi

shopt -s nullglob
inplace_state=("$TARGET_DIR"/*_semantic_work.json)
if (( ${#inplace_state[@]} > 0 )); then
  rm -f "${inplace_state[@]}"
  echo "[OK] Removed ${#inplace_state[@]} in-place state file(s)"
else
  echo "[SKIP] No in-place state files"
fi

if [[ "$FORCE" == "1" ]]; then
  out_files=("$TARGET_DIR"/*_out_*.json)
  ts_files=("$TARGET_DIR"/*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json)
  count=0
  if (( ${#out_files[@]} > 0 )); then
    rm -f "${out_files[@]}"
    count=$((count + ${#out_files[@]}))
  fi
  if (( ${#ts_files[@]} > 0 )); then
    rm -f "${ts_files[@]}"
    count=$((count + ${#ts_files[@]}))
  fi
  echo "[OK] Force removed $count generated output file(s)"
fi

echo "[DONE] Semantic state reset complete."

