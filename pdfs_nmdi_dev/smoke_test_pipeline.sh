#!/usr/bin/env bash
set -euo pipefail

# Useful smoke test:
# - validates script syntax/importability
# - validates stage-2 manifest-driven run from shared scripts dir into a target index dir
# - fails non-zero with explicit reason if any step regresses

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${VENV_PYTHON:-$PROJECT_DIR/venv/bin/python}"

fail() {
  echo "[FAIL] $*" >&2
  exit 1
}

pass() {
  echo "[PASS] $*"
}

[[ -x "$PYTHON_BIN" ]] || fail "Python not executable: $PYTHON_BIN"

TMPDIR="$(mktemp -d /tmp/pdfs_pipeline_smoke_XXXXXX)"
trap 'rm -rf "$TMPDIR"' EXIT
INDEX_DIR="$TMPDIR/index_a"
mkdir -p "$INDEX_DIR"

pass "Temp sandbox: $TMPDIR"

cd "$SCRIPT_DIR"
"$PYTHON_BIN" -m py_compile \
  batch_pdf_2_json.py batch_semantic_rechunk.py semantic_rechunk_qwen3.py \
  filter_non_book_content.py improve_questions.py improve_summaries.py \
  postprocess_llm_common.py llm_rechunk.py prechunk.py \
  || fail "py_compile failed"
bash -n run_semantic_batch.sh || fail "run_semantic_batch.sh syntax failed"
bash -n restart_semantic_batch_nohup.sh || fail "restart_semantic_batch_nohup.sh syntax failed"
pass "Syntax/import checks"

# Create synthetic stage-1 artifacts in target index directory.
cat > "$INDEX_DIR/sample_chunks.json" <<'JSON'
[
  {"input":"s1","output":"alpha bravo charlie","summary":""},
  {"input":"s2","output":"delta echo foxtrot","summary":""}
]
JSON

cat > "$INDEX_DIR/stage1_json_manifest.json" <<JSON
{
  "generated_at": "2026-03-15T00:00:00Z",
  "generator": "batch_pdf_2_json.py",
  "cwd": "$INDEX_DIR",
  "files": [
    {"pdf_file":"sample.pdf","output_json":"sample_chunks.json","status":"existing","exists":true}
  ]
}
JSON

# Run stage-2 from shared script dir into target dir.
set +e
"$SCRIPT_DIR/run_semantic_batch.sh" "$INDEX_DIR" \
  --dry-run --max-passes 1 --skip-postprocess --status-file semantic_batch_status.json --work-dir .semantic_work
RC=$?
set -e

[[ $RC -eq 1 ]] || fail "Expected dry-run rc=1 (incomplete), got rc=$RC"
[[ -f "$INDEX_DIR/semantic_batch_status.json" ]] || fail "Missing semantic_batch_status.json in target dir"
[[ -f "$INDEX_DIR/.semantic_work/semantic_batch_inputs.json" ]] || fail "Missing semantic_batch_inputs.json in target dir"

"$PYTHON_BIN" - <<PY || fail "Status validation failed"
import json
status=json.load(open("$INDEX_DIR/semantic_batch_status.json","r",encoding="utf-8"))
inputs=json.load(open("$INDEX_DIR/.semantic_work/semantic_batch_inputs.json","r",encoding="utf-8"))
assert isinstance(status, dict)
assert isinstance(inputs, dict)
assert len(status.get("passes", [])) >= 1
tracked=inputs.get("inputs", [])
assert len(tracked) == 1
assert tracked[0].get("input_file","").endswith("sample_chunks.json")
print("ok")
PY

pass "Manifest-driven target-dir run"
pass "Smoke test completed successfully"
