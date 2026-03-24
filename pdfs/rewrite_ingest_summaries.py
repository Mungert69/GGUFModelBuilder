#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from improve_summaries import build_prompt, extract_summary
from postprocess_llm_common import create_client_from_config, load_runtime_config, safe_chat_completion


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))


def sha1_text(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def file_signature(path: str) -> Dict[str, Any]:
    st = os.stat(path)
    return {
        "size": int(st.st_size),
        "mtime_ns": int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))),
    }


def payload_signature(payload: Any) -> Dict[str, Any]:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "rows": len(payload) if isinstance(payload, list) else 0,
        "sha1": hashlib.sha1(raw.encode("utf-8")).hexdigest(),
    }


def source_signature(payload: Any) -> str:
    """
    Signature for resume-compatibility based on stable source content.
    Intentionally excludes mutable fields like rewritten summaries.
    """
    items = []
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                items.append({"kind": "non_dict"})
                continue
            items.append(
                {
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "chunk_start": row.get("chunk_start"),
                    "chunk_end": row.get("chunk_end"),
                    "output_sha1": sha1_text(str(row.get("output") or "")),
                }
            )
    raw = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def atomic_save_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_status(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"started_at": now_iso(), "updated_at": now_iso(), "version": 1, "files": {}}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        return {"started_at": now_iso(), "updated_at": now_iso(), "version": 1, "files": {}}
    payload.setdefault("files", {})
    payload.setdefault("version", 1)
    payload["updated_at"] = now_iso()
    return payload


def discover_files(index_dir: str, pattern: str) -> List[str]:
    if os.path.isabs(pattern):
        return sorted([p for p in glob.glob(pattern) if os.path.isfile(p)])
    return sorted([p for p in glob.glob(os.path.join(index_dir, pattern)) if os.path.isfile(p)])


def ensure_file_state(
    status: Dict[str, Any],
    file_path: str,
    payload: List[Dict[str, Any]],
    summary_token_cap: int,
) -> Dict[str, Any]:
    files = status.setdefault("files", {})
    state = files.get(file_path)
    cur_file_sig = file_signature(file_path)
    cur_payload_sig = payload_signature(payload)
    cur_source_sig = source_signature(payload)
    if not isinstance(state, dict):
        state = {}
    state.setdefault("done_indices", [])
    state.setdefault("records", {})
    state.setdefault("stats", {"rewritten": 0, "skipped": 0, "failed": 0})

    compatible = (
        state.get("summary_token_cap") == int(summary_token_cap)
        and state.get("source_signature") == cur_source_sig
        and int(state.get("rows_total") or 0) == (len(payload) if isinstance(payload, list) else 0)
    )
    if not compatible:
        state["done_indices"] = []
        state["records"] = {}
        state["stats"] = {"rewritten": 0, "skipped": 0, "failed": 0}
        state["reset_at"] = now_iso()

    state["summary_token_cap"] = int(summary_token_cap)
    state["rows_total"] = len(payload) if isinstance(payload, list) else 0
    state["source_signature"] = cur_source_sig
    state["file_signature"] = cur_file_sig
    state["payload_signature"] = cur_payload_sig
    state["updated_at"] = now_iso()
    files[file_path] = state
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite summaries in ingest JSON files with sparse-safe retry.")
    parser.add_argument("--index-dir", default="securitybooks")
    parser.add_argument("--pattern", default="*_semantic_ingest.json")
    parser.add_argument("--config", default="", help="Runtime config JSON (default: postprocess_config.json)")
    parser.add_argument("--status-file", default="")
    parser.add_argument("--summary-token-cap", type=int, default=4096)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-rows-per-file", type=int, default=0)
    parser.add_argument("--max-tokens", type=int, default=320, help="LLM max_tokens for summary generation")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    index_dir = os.path.abspath(args.index_dir)
    files = discover_files(index_dir=index_dir, pattern=args.pattern)
    if args.max_files > 0:
        files = files[: args.max_files]

    if not files:
        print(f"[INFO] No files found under {index_dir} matching {args.pattern}")
        return

    status_file = args.status_file.strip() or os.path.join(index_dir, ".rewrite_ingest_summaries_status.json")
    status = load_status(status_file)

    config = load_runtime_config(args.config or None)
    if args.dry_run:
        client = None
        model = ""
        controller = None
    else:
        client, model, _, controller = create_client_from_config(config)

    print(f"[INFO] Started at {now_iso()}")
    print(f"[INFO] files={len(files)} summary_token_cap={args.summary_token_cap} dry_run={args.dry_run}")
    print(f"[INFO] status_file={status_file}")

    run_results: List[Dict[str, Any]] = []
    for file_path in files:
        print(f"[FILE] {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            print(f"[WARN] skip_not_list: {file_path}")
            run_results.append({"file": file_path, "status": "skip_not_list"})
            continue

        state = ensure_file_state(status, file_path, payload, args.summary_token_cap)
        done = set(int(x) for x in state.get("done_indices", []))
        records = state.setdefault("records", {})
        stats = state.setdefault("stats", {"rewritten": 0, "skipped": 0, "failed": 0})

        file_rewritten = 0
        file_skipped = 0
        file_failed = 0
        processed = 0

        for idx, row in enumerate(payload):
            if idx in done:
                continue
            if args.max_rows_per_file > 0 and processed >= args.max_rows_per_file:
                break
            processed += 1

            if not isinstance(row, dict):
                rec = {"state": "skipped_not_object", "updated_at": now_iso()}
                records[str(idx)] = rec
                done.add(idx)
                file_skipped += 1
                stats["skipped"] = int(stats.get("skipped", 0)) + 1
            else:
                summary_before = str(row.get("summary") or "")
                summary_before_tokens = estimate_tokens(summary_before)
                output_text = str(row.get("output") or "")
                output_tokens = estimate_tokens(output_text)

                if not summary_before.strip():
                    records[str(idx)] = {
                        "state": "skipped_missing_summary",
                        "summary_tokens_before": summary_before_tokens,
                        "updated_at": now_iso(),
                    }
                    done.add(idx)
                    file_skipped += 1
                    stats["skipped"] = int(stats.get("skipped", 0)) + 1
                elif summary_before_tokens >= int(args.summary_token_cap):
                    records[str(idx)] = {
                        "state": "skipped_summary_over_cap",
                        "summary_tokens_before": summary_before_tokens,
                        "output_tokens": output_tokens,
                        "updated_at": now_iso(),
                    }
                    done.add(idx)
                    file_skipped += 1
                    stats["skipped"] = int(stats.get("skipped", 0)) + 1
                elif output_tokens >= int(args.summary_token_cap):
                    records[str(idx)] = {
                        "state": "skipped_output_over_cap",
                        "summary_tokens_before": summary_before_tokens,
                        "output_tokens": output_tokens,
                        "updated_at": now_iso(),
                    }
                    done.add(idx)
                    file_skipped += 1
                    stats["skipped"] = int(stats.get("skipped", 0)) + 1
                elif not output_text.strip():
                    records[str(idx)] = {
                        "state": "skipped_missing_output",
                        "summary_tokens_before": summary_before_tokens,
                        "output_tokens": output_tokens,
                        "updated_at": now_iso(),
                    }
                    done.add(idx)
                    file_skipped += 1
                    stats["skipped"] = int(stats.get("skipped", 0)) + 1
                else:
                    try:
                        prompt = build_prompt(text=output_text)
                        if args.dry_run:
                            new_summary = summary_before
                        else:
                            raw = safe_chat_completion(
                                client=client,
                                controller=controller,
                                model=model,
                                prompt_text=prompt,
                                max_tokens=int(args.max_tokens),
                                temperature=0.2,
                                call_label="rewrite_ingest_summary",
                                call_meta={
                                    "source_file": row.get("source_file", ""),
                                    "chunk_start": row.get("chunk_start", ""),
                                    "chunk_end": row.get("chunk_end", ""),
                                    "row_index": idx,
                                },
                            )
                            new_summary = extract_summary(raw)

                        if not new_summary.strip():
                            raise RuntimeError("Empty summary from model")

                        row["summary"] = new_summary
                        records[str(idx)] = {
                            "state": "rewritten",
                            "summary_tokens_before": summary_before_tokens,
                            "output_tokens": output_tokens,
                            "summary_tokens_after": estimate_tokens(new_summary),
                            "summary_sha1_before": sha1_text(summary_before),
                            "summary_sha1_after": sha1_text(new_summary),
                            "updated_at": now_iso(),
                        }
                        done.add(idx)
                        file_rewritten += 1
                        stats["rewritten"] = int(stats.get("rewritten", 0)) + 1
                    except Exception as exc:
                        records[str(idx)] = {
                            "state": "failed",
                            "error": str(exc),
                            "summary_tokens_before": summary_before_tokens,
                            "output_tokens": output_tokens,
                            "updated_at": now_iso(),
                            "attempts": int(records.get(str(idx), {}).get("attempts", 0)) + 1,
                        }
                        file_failed += 1
                        stats["failed"] = int(stats.get("failed", 0)) + 1
                    except KeyboardInterrupt:
                        records[str(idx)] = {
                            "state": "interrupted",
                            "error": "KeyboardInterrupt",
                            "summary_tokens_before": summary_before_tokens,
                            "output_tokens": output_tokens,
                            "updated_at": now_iso(),
                            "attempts": int(records.get(str(idx), {}).get("attempts", 0)) + 1,
                        }
                        state["done_indices"] = sorted(done)
                        state["updated_at"] = now_iso()
                        status["updated_at"] = now_iso()
                        if not args.dry_run:
                            atomic_save_json(file_path, payload)
                            atomic_save_json(status_file, status)
                        print(
                            f"[INTERRUPT] file={file_path} row_index={idx} "
                            "state_saved=true next_run_will_retry_row=true"
                        )
                        return

            state["done_indices"] = sorted(done)
            state["updated_at"] = now_iso()
            status["updated_at"] = now_iso()
            if not args.dry_run:
                atomic_save_json(file_path, payload)
                atomic_save_json(status_file, status)

        result = {
            "file": file_path,
            "rewritten": file_rewritten,
            "skipped": file_skipped,
            "failed": file_failed,
            "done_indices": len(state.get("done_indices", [])),
            "rows_total": len(payload),
        }
        run_results.append(result)
        print(f"[RESULT] {result}")

    print("[SUMMARY]")
    print(json.dumps({"results": run_results, "updated_at": now_iso()}, ensure_ascii=False, indent=2))

    if not args.dry_run:
        status["updated_at"] = now_iso()
        atomic_save_json(status_file, status)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("[INTERRUPT] stopped by user")
