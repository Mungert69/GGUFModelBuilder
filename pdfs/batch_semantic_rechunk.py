import argparse
import glob
import json
import os
import re
import hashlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


DATE_SUFFIX_RE = re.compile(r"_\d{14}\.json$")


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def discover_input_files(pattern):
    files = sorted(glob.glob(pattern))
    return [f for f in files if os.path.isfile(f) and is_stage1_source_json(f)]


def is_stage1_source_json(path):
    """
    Keep only stage-1 source JSON chunk files and ignore generated artifacts from stage-2.
    """
    name = os.path.basename(path)
    lower = name.lower()

    # Keep non-JSON patterns untouched (defensive; current workflow uses JSON files).
    if not lower.endswith(".json"):
        return True

    # Exclude generated stage-2 outputs/status/retry artifacts.
    if lower.startswith("retry_"):
        return False
    if lower.startswith("semantic_batch_status"):
        return False
    if "_out_" in lower:
        return False
    if lower.endswith("_semantic_work.json"):
        return False
    if lower.endswith("_semantic_ingest.json"):
        return False
    if DATE_SUFFIX_RE.search(lower):
        return False

    return True


def load_json_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def to_int_or_none(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def first_non_empty(chunks, keys):
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for key in keys:
            value = chunk.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
    return ""


def normalize_section_path(value):
    if value is None:
        return ""
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return " > ".join(parts)
    return str(value).strip()


def extract_page_bounds(chunks):
    starts = []
    ends = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue

        start_val = chunk.get("start_page", chunk.get("page_start"))
        end_val = chunk.get("end_page", chunk.get("page_end"))
        if start_val is None:
            start_val = chunk.get("page")
        if end_val is None:
            end_val = chunk.get("page")

        start_i = to_int_or_none(start_val)
        end_i = to_int_or_none(end_val)
        if start_i is not None:
            starts.append(start_i)
        if end_i is not None:
            ends.append(end_i)

    page_start = min(starts) if starts else None
    page_end = max(ends) if ends else None
    return page_start, page_end


def build_doc_id(input_file, source_title, source_chunk_total):
    payload = f"{os.path.basename(input_file)}|{source_title}|{source_chunk_total}"
    return "doc_" + hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_ingest_records_from_work(input_file, work_file):
    source_chunks = load_json_file(input_file)
    if not isinstance(source_chunks, list):
        raise ValueError(f"{input_file} must be a JSON list.")

    blocks = load_json_file(work_file)
    if not isinstance(blocks, list):
        raise ValueError(f"{work_file} must be a JSON list.")

    source_chunk_total = len(source_chunks)
    source_title = first_non_empty(source_chunks, ["source_title", "book_title", "title"])
    if not source_title:
        source_title = os.path.splitext(os.path.basename(input_file))[0]

    def should_keep_block(block):
        value = block.get("is_book_content", True)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("no", "false", "0", "n"):
                return False
            if normalized in ("yes", "true", "1", "y"):
                return True
        return True

    filtered_blocks = [b for b in blocks if isinstance(b, dict) and should_keep_block(b)]
    dropped = len(blocks) - len(filtered_blocks)
    if dropped > 0:
        print(f"[FILTER] Dropping {dropped} non-content blocks from ingest export for {input_file}")

    doc_id = build_doc_id(input_file, source_title, source_chunk_total)
    chunk_total = len(filtered_blocks)
    records = []

    for idx, block in enumerate(filtered_blocks, start=1):
        start = to_int_or_none(block.get("start")) or idx
        end = to_int_or_none(block.get("end")) or start

        if start < 1:
            start = 1
        if end < start:
            end = start
        if source_chunk_total > 0 and start > source_chunk_total:
            start = source_chunk_total
        if source_chunk_total > 0 and end > source_chunk_total:
            end = source_chunk_total

        covered = source_chunks[start - 1 : end] if source_chunk_total > 0 else []
        page_start, page_end = extract_page_bounds(covered)
        section_path = normalize_section_path(
            first_non_empty(covered, ["section_path", "section_title", "chapter_title", "chapter", "heading"])
        )
        source_title_local = first_non_empty(covered, ["source_title", "book_title", "title"]) or source_title

        record = {
            "input": block.get("question", ""),
            "summary": block.get("summary", ""),
            "output": block.get("text", ""),
            "doc_id": doc_id,
            "chunk_id": f"{doc_id}:chunk_{idx:05d}",
            "chunk_index": idx,
            "chunk_count": chunk_total,
            "chunk_start": start,
            "chunk_end": end,
            "semantic_block_index": to_int_or_none(block.get("semantic_block_index")) or idx,
            "source_title": source_title_local,
            "source_file": os.path.basename(input_file),
            "source_chunk_total": source_chunk_total,
            "section_path": section_path,
            "page_start": page_start if page_start is not None else "",
            "page_end": page_end if page_end is not None else "",
            "prev_chunk_id": "",
            "next_chunk_id": "",
        }
        records.append(record)

    for i, record in enumerate(records):
        if i > 0:
            record["prev_chunk_id"] = records[i - 1]["chunk_id"]
        if i + 1 < len(records):
            record["next_chunk_id"] = records[i + 1]["chunk_id"]

    return records


def default_ingest_output_file(input_file):
    base = os.path.splitext(os.path.basename(input_file))[0]
    directory = os.path.dirname(input_file) or "."
    return os.path.join(directory, f"{base}_semantic_ingest.json")


def export_ingest_file(input_file, work_file, output_file):
    records = build_ingest_records_from_work(input_file, work_file)
    write_json_file(output_file, records)
    print(f"[EXPORT] Wrote {len(records)} records to {output_file}")
    return output_file


def load_chunk_count(input_file):
    data = load_json_file(input_file)
    if not isinstance(data, list):
        raise ValueError("Input JSON must be a list.")
    return len(data)


def semantic_output_candidates(input_file):
    base = os.path.splitext(os.path.basename(input_file))[0]
    candidates = glob.glob(f"{base}_*.json")
    results = []
    prefix = f"{base}_"
    for path in candidates:
        name = os.path.basename(path)
        if "_out_" in name:
            continue
        if not name.startswith(prefix):
            continue
        if not DATE_SUFFIX_RE.search(name):
            continue
        results.append(path)
    return sorted(results, key=os.path.getmtime)


def contiguous_ranges(indices):
    if not indices:
        return []
    ranges = []
    start = prev = indices[0]
    for value in indices[1:]:
        if value == prev + 1:
            prev = value
            continue
        ranges.append([start, prev])
        start = prev = value
    ranges.append([start, prev])
    return ranges


def compute_coverage(block_file, total_chunks):
    blocks = load_json_file(block_file)
    if not isinstance(blocks, list):
        raise ValueError("Block output must be a list.")

    covered = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        start = block.get("start", 0)
        end = block.get("end", 0)
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start <= 0 or end < start:
            continue
        start = max(1, start)
        end = min(total_chunks, end)
        covered.update(range(start, end + 1))

    missing = [i for i in range(1, total_chunks + 1) if i not in covered]
    ranges = contiguous_ranges(missing)
    return {
        "block_count": len(blocks),
        "covered_count": len(covered),
        "missing_count": len(missing),
        "missing_sample": missing[:20],
        "missing_ranges": ranges[:200],
        "is_complete": len(missing) == 0
    }


def default_work_file(input_file, work_dir=None):
    base = os.path.splitext(os.path.basename(input_file))[0]
    directory = work_dir if work_dir else (os.path.dirname(input_file) or ".")
    return os.path.join(directory, f"{base}_semantic_work.json")


def seed_work_file_if_needed(input_file, work_file):
    if os.path.exists(work_file):
        return False
    candidates = semantic_output_candidates(input_file)
    if not candidates:
        return False
    latest = candidates[-1]
    shutil.copy2(latest, work_file)
    print(f"[SEED] {work_file} seeded from {latest}")
    return True


def analyze_input(input_file, work_file=None):
    result = {
        "input_file": input_file,
        "work_file": work_file or "",
        "status": "unknown",
        "error": "",
        "total_chunks": 0,
        "latest_block_file": "",
        "latest_block_mtime": "",
        "coverage": {}
    }
    try:
        total_chunks = load_chunk_count(input_file)
        result["total_chunks"] = total_chunks
        if total_chunks == 0:
            result["coverage"] = {
                "block_count": 0,
                "covered_count": 0,
                "missing_count": 0,
                "missing_sample": [],
                "missing_ranges": [],
                "is_complete": True
            }
            result["status"] = "complete"
            return result

        block_file = ""
        if work_file and os.path.exists(work_file):
            block_file = work_file
        else:
            candidates = semantic_output_candidates(input_file)
            if candidates:
                block_file = candidates[-1]

        if not block_file:
            result["status"] = "no_output"
            return result

        result["latest_block_file"] = block_file
        result["latest_block_mtime"] = datetime.fromtimestamp(
            os.path.getmtime(block_file), tz=timezone.utc).replace(microsecond=0).isoformat()
        coverage = compute_coverage(block_file, total_chunks)
        result["coverage"] = coverage
        result["status"] = "complete" if coverage["is_complete"] else "incomplete"
        return result
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
        return result


def write_status_file(status_file, payload):
    write_json_file(status_file, payload)


def run_semantic(script_path, input_file, output_file=None, resume=False):
    cmd = [sys.executable, script_path, input_file]
    if output_file:
        cmd.append(output_file)
    if resume:
        cmd.append("--resume")
    cmd.append("--single")
    print(f"[RUN] {' '.join(cmd)}")
    completed = subprocess.run(cmd, check=False)
    return completed.returncode


def select_retry_range(analysis):
    coverage = analysis.get("coverage") or {}
    ranges = coverage.get("missing_ranges") or []
    if ranges:
        return ranges[0]
    total = analysis.get("total_chunks") or 0
    if total > 0:
        return [1, total]
    return None


def map_block_ranges(blocks, offset, range_start, range_end):
    mapped = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        start = block.get("start")
        end = block.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        gstart = start + offset
        gend = end + offset
        if gend < range_start or gstart > range_end:
            continue
        gstart = max(range_start, gstart)
        gend = min(range_end, gend)
        if gstart > gend:
            continue
        item = dict(block)
        item["start"] = gstart
        item["end"] = gend
        mapped.append(item)
    return mapped


def merge_blocks_for_range(work_file, range_start, range_end, mapped_blocks):
    existing = []
    if os.path.exists(work_file):
        payload = load_json_file(work_file)
        if isinstance(payload, list):
            existing = payload
    kept = []
    for block in existing:
        if not isinstance(block, dict):
            continue
        start = block.get("start")
        end = block.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if end < range_start or start > range_end:
            kept.append(block)
    merged = kept + mapped_blocks
    merged.sort(key=lambda b: (b.get("start", 10**9), b.get("end", 10**9)))
    write_json_file(work_file, merged)


def retry_missing_range(
    script_path,
    input_file,
    work_file,
    range_start,
    range_end,
    keep_temp=False,
    retry_state_root=""
):
    input_data = load_json_file(input_file)
    if not isinstance(input_data, list):
        raise ValueError(f"{input_file} must be a JSON list.")
    subset = input_data[range_start - 1:range_end]
    if not subset:
        return {"return_code": 0, "new_blocks": 0, "range": [range_start, range_end], "note": "empty_range"}

    if retry_state_root:
        os.makedirs(retry_state_root, exist_ok=True)
        safe_base = os.path.splitext(os.path.basename(input_file))[0]
        temp_dir = os.path.join(retry_state_root, safe_base)
        os.makedirs(temp_dir, exist_ok=True)
    else:
        temp_dir = tempfile.mkdtemp(prefix="semantic_retry_")
    temp_input = os.path.join(temp_dir, f"retry_{range_start}_{range_end}_chunks.json")
    if not os.path.exists(temp_input):
        write_json_file(temp_input, subset)
    temp_output = os.path.join(temp_dir, f"retry_{range_start}_{range_end}_semantic_blocks.json")
    rc = run_semantic(script_path, temp_input, output_file=temp_output, resume=True)

    mapped_count = 0
    latest_block_file = ""
    produced_path = ""
    if os.path.exists(temp_output):
        produced_path = temp_output
    else:
        # Backward compatibility: older single-file mode rewrote output path with a timestamp suffix.
        stem, ext = os.path.splitext(temp_output)
        candidates = sorted(glob.glob(f"{stem}_*{ext}"), key=os.path.getmtime)
        if candidates:
            produced_path = candidates[-1]

    if produced_path:
        latest_block_file = produced_path
        produced = load_json_file(produced_path)
        if isinstance(produced, list):
            mapped = map_block_ranges(produced, range_start - 1, range_start, range_end)
            mapped_count = len(mapped)
            if mapped:
                merge_blocks_for_range(work_file, range_start, range_end, mapped)

    if not keep_temp and not retry_state_root:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass

    return {
        "return_code": rc,
        "new_blocks": mapped_count,
        "range": [range_start, range_end],
        "temp_block_file": latest_block_file,
        "temp_input_file": temp_input
    }


def main():
    parser = argparse.ArgumentParser(
        description="Stage-2 batch loop: run semantic rechunk and verify chunk coverage.")
    parser.add_argument("--pattern", default="*.json", help="Input file glob pattern.")
    parser.add_argument("--max-passes", type=int, default=10, help="Maximum loop passes.")
    parser.add_argument("--status-file", default="semantic_batch_status.json", help="Status output file path.")
    parser.add_argument("--script", default=os.path.join(os.path.dirname(__file__), "semantic_rechunk_qwen3.py"),
                        help="Path to semantic rechunk script.")
    parser.add_argument("--work-dir", default="", help="Directory for persistent per-file semantic work outputs.")
    parser.add_argument(
        "--ingest-output-dir",
        default="",
        help="Optional directory for final merged ingest JSON outputs. Default: alongside each input file.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, do not execute semantic script.")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary retry files for debugging.")
    parser.add_argument(
        "--allow-zero-progress-pass",
        action="store_true",
        help="Do not fail-fast when a pass merges zero new blocks.",
    )
    args = parser.parse_args()

    input_files = discover_input_files(args.pattern)
    if not input_files:
        print(f"[INFO] No input files found for pattern: {args.pattern}")
        return 0

    work_dir = args.work_dir.strip()
    if work_dir:
        os.makedirs(work_dir, exist_ok=True)

    work_files = {f: default_work_file(f, work_dir=work_dir if work_dir else None) for f in input_files}
    for input_file, work_file in work_files.items():
        seed_work_file_if_needed(input_file, work_file)
    retry_state_root = os.path.join(work_dir if work_dir else ".", ".retry_state")
    os.makedirs(retry_state_root, exist_ok=True)

    overall = {
        "started_at": utc_now_iso(),
        "pattern": args.pattern,
        "max_passes": args.max_passes,
        "work_files": work_files,
        "passes": []
    }
    aborted_no_progress = False

    for pass_num in range(1, args.max_passes + 1):
        analyses_before = [analyze_input(f, work_files.get(f)) for f in input_files]
        pending = [a for a in analyses_before if a["status"] in ("no_output", "incomplete", "error")]

        pass_info = {
            "pass": pass_num,
            "started_at": utc_now_iso(),
            "pending_before_count": len(pending),
            "pending_before": [p["input_file"] for p in pending],
            "runs": []
        }

        if not pending:
            pass_info["ended_at"] = utc_now_iso()
            pass_info["message"] = "All inputs complete."
            overall["passes"].append(pass_info)
            break

        for item in pending:
            input_file = item["input_file"]
            retry_range = select_retry_range(item)
            run_entry = {
                "input_file": input_file,
                "work_file": work_files.get(input_file),
                "return_code": None,
                "retry_range": retry_range
            }
            if args.dry_run:
                run_entry["return_code"] = 0
                run_entry["dry_run"] = True
            else:
                if not retry_range:
                    run_entry["return_code"] = 1
                    run_entry["error"] = "No retry range available."
                else:
                    result = retry_missing_range(
                        script_path=args.script,
                        input_file=input_file,
                        work_file=work_files[input_file],
                        range_start=retry_range[0],
                        range_end=retry_range[1],
                        keep_temp=args.keep_temp,
                        retry_state_root=retry_state_root
                    )
                    run_entry.update(result)
                    run_entry["return_code"] = result.get("return_code")
            pass_info["runs"].append(run_entry)
            print(
                f"[RUN-RESULT] file={os.path.basename(input_file)} "
                f"rc={run_entry.get('return_code')} "
                f"new_blocks={run_entry.get('new_blocks', 0)} "
                f"range={run_entry.get('range') or run_entry.get('retry_range')}"
            )

        analyses_after = [analyze_input(f, work_files.get(f)) for f in input_files]
        incomplete_after = [a for a in analyses_after if a["status"] in ("no_output", "incomplete", "error")]
        new_blocks_total = sum((r.get("new_blocks") or 0) for r in pass_info["runs"])
        rc_failures = sum(1 for r in pass_info["runs"] if (r.get("return_code") or 0) != 0)
        zero_merge_runs = sum(1 for r in pass_info["runs"] if (r.get("new_blocks") or 0) == 0)
        pass_info["new_blocks_total"] = new_blocks_total
        pass_info["return_code_failures"] = rc_failures
        pass_info["zero_merge_runs"] = zero_merge_runs
        pass_info["pending_after_count"] = len(incomplete_after)
        pass_info["pending_after"] = [p["input_file"] for p in incomplete_after]
        pass_info["analyses"] = analyses_after
        pass_info["ended_at"] = utc_now_iso()
        overall["passes"].append(pass_info)

        write_status_file(args.status_file, overall)
        print(
            f"[PASS {pass_num}] incomplete_after={len(incomplete_after)} "
            f"new_blocks_total={new_blocks_total} rc_failures={rc_failures}"
        )

        if (
            not args.dry_run
            and pending
            and new_blocks_total == 0
            and len(incomplete_after) == len(pending)
            and not args.allow_zero_progress_pass
        ):
            aborted_no_progress = True
            print(
                "[FATAL] Zero merged progress in this pass while work remains incomplete. "
                "Stopping early to avoid wasted runtime. "
                "Use --allow-zero-progress-pass to override."
            )
            break

        if not incomplete_after:
            break

    analyses_final = [analyze_input(f, work_files.get(f)) for f in input_files]
    for analysis in analyses_final:
        if analysis.get("status") != "complete":
            continue
        input_file = analysis["input_file"]
        work_file = work_files.get(input_file) or ""
        if not work_file or not os.path.exists(work_file):
            continue
        try:
            if args.ingest_output_dir.strip():
                os.makedirs(args.ingest_output_dir, exist_ok=True)
                out_name = f"{os.path.splitext(os.path.basename(input_file))[0]}_semantic_ingest.json"
                out_file = os.path.join(args.ingest_output_dir, out_name)
            else:
                out_file = default_ingest_output_file(input_file)
            export_ingest_file(input_file, work_file, out_file)
        except Exception as exc:
            print(f"[WARN] Failed to export ingest file for {input_file}: {exc!r}")

    overall["ended_at"] = utc_now_iso()
    write_status_file(args.status_file, overall)

    latest = overall["passes"][-1] if overall["passes"] else {}
    remaining = latest.get("pending_after_count", 0)
    if remaining == 0:
        print("[DONE] All input files have full chunk coverage.")
        return 0

    if aborted_no_progress:
        print(f"[FATAL] Aborted after zero-progress pass. Remaining incomplete files: {remaining}.")
        return 2

    print(f"[WARN] Completed passes with {remaining} file(s) still incomplete.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
