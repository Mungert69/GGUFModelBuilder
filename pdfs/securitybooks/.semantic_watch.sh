#!/usr/bin/env bash
set -u
cd /home/mahadeva/code/GGUFModelBuilder/pdfs/securitybooks || exit 1
while true; do
  {
    echo "===== $(date -u +%Y-%m-%dT%H:%M:%SZ) ====="
    pgrep -af "batch_semantic_rechunk.py|semantic_rechunk_qwen3.py" || echo "[WARN] no batch/semantic process"
    f=".semantic_work/.retry_state/A_Bug_Hunters_Diary_/retry_1_125_semantic_blocks.json"
    if [[ -f "$f" ]]; then
      ls -lh "$f"
    fi
    tail -n 20 semantic_batch.log 2>/dev/null || true
    echo
  } >> semantic_watch.log 2>&1
  sleep 300
done
