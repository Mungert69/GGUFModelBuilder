#!/usr/bin/env python3
import argparse
import glob
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from improve_questions import build_prompt as build_questions_prompt
from improve_questions import extract_scored_question_candidates
from improve_summaries import build_prompt as build_summary_prompt
from improve_summaries import extract_summary
from postprocess_llm_common import (
    create_client_from_config,
    load_runtime_config,
    safe_chat_completion,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def atomic_save_json(path: str, payload: Any) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{path}.tmp.{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def parse_int(raw: str, lower: int, upper: int) -> Optional[int]:
    if not raw:
        return None
    m = re.findall(r"\b(\d{1,4})\b", raw)
    if not m:
        return None
    value = int(m[-1])
    if value < lower or value > upper:
        return None
    return value


def build_boundary_prompt(chunk_texts: List[str], token_cap: int) -> str:
    lines = [
        "You are splitting technical content into coherent RAG chunks.",
        "Choose how many leading chunks should be included in the NEXT chunk.",
        "Return ONLY one integer N.",
        "Constraints:",
        f"- 1 <= N <= {len(chunk_texts)}",
        f"- The merged text must stay within about {token_cap} tokens.",
        "- Prefer semantic boundaries (heading/topic transition) when possible.",
        "- If uncertain, choose a smaller safe N.",
        "",
        "Candidate chunks:",
    ]
    for idx, text in enumerate(chunk_texts, start=1):
        preview = (text or "").strip().replace("\n", " ")
        if len(preview) > 450:
            preview = preview[:450] + " ..."
        lines.append(
            f"[{idx}] tok~{estimate_tokens(text)} :: {preview}"
        )
    lines.append("")
    lines.append("Return only N.")
    return "\n".join(lines)


def split_single_text(text: str, token_cap: int) -> List[str]:
    if estimate_tokens(text) <= token_cap:
        return [text]

    out: List[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", text or "") if p.strip()]
    if not paragraphs:
        paragraphs = [text or ""]

    cur: List[str] = []
    cur_tokens = 0

    def flush() -> None:
        nonlocal cur, cur_tokens
        if cur:
            out.append("\n\n".join(cur).strip())
        cur = []
        cur_tokens = 0

    for para in paragraphs:
        t = estimate_tokens(para)
        if t > token_cap:
            # Sentence-level fallback.
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
            if not sentences:
                sentences = [para]
            for sentence in sentences:
                st = estimate_tokens(sentence)
                if st > token_cap:
                    # Hard fallback by characters.
                    flush()
                    hard_size = max(1200, int(len(sentence) * (token_cap / max(1, st))))
                    for i in range(0, len(sentence), hard_size):
                        piece = sentence[i : i + hard_size].strip()
                        if piece:
                            out.append(piece)
                    continue
                if cur_tokens + st > token_cap and cur:
                    flush()
                cur.append(sentence)
                cur_tokens += st
            continue

        if cur_tokens + t > token_cap and cur:
            flush()
        cur.append(para)
        cur_tokens += t

    flush()
    return [x for x in out if x.strip()]


@dataclass
class Piece:
    text: str
    chunk_start: int
    chunk_end: int


def split_large_record_with_llm(
    source_texts: List[str],
    abs_start: int,
    token_cap: int,
    max_window: int,
    client: Any,
    controller: Any,
    model: str,
    parent_chunk_id: str = "",
    source_file: str = "",
) -> List[Piece]:
    pieces: List[Piece] = []
    p = 0
    n_total = len(source_texts)

    while p < n_total:
        window = source_texts[p : p + max_window]
        if not window:
            break

        if len(window) == 1:
            only = window[0]
            if estimate_tokens(only) <= token_cap:
                pieces.append(Piece(text=only, chunk_start=abs_start + p, chunk_end=abs_start + p))
            else:
                subs = split_single_text(only, token_cap=token_cap)
                for sub in subs:
                    pieces.append(Piece(text=sub, chunk_start=abs_start + p, chunk_end=abs_start + p))
            p += 1
            continue

        prompt = build_boundary_prompt(window, token_cap=token_cap)
        raw = safe_chat_completion(
            client=client,
            controller=controller,
            model=model,
            prompt_text=prompt,
            max_tokens=32,
            temperature=0.0,
            call_label="stage5_boundary",
            call_meta={
                "source_file": source_file,
                "parent_chunk_id": parent_chunk_id,
                "abs_start": abs_start + p,
                "window_size": len(window),
                "token_cap": token_cap,
            },
        )
        proposed_n = parse_int(raw, 1, len(window)) or 1

        chosen_n = proposed_n
        while chosen_n > 1:
            merged = "\n".join(window[:chosen_n])
            if estimate_tokens(merged) <= token_cap:
                break
            chosen_n -= 1

        first_tok = estimate_tokens(window[0])
        if chosen_n == 1 and first_tok > token_cap:
            subs = split_single_text(window[0], token_cap=token_cap)
            for sub in subs:
                pieces.append(Piece(text=sub, chunk_start=abs_start + p, chunk_end=abs_start + p))
            p += 1
            continue

        merged = "\n".join(window[:chosen_n]).strip()
        pieces.append(
            Piece(
                text=merged,
                chunk_start=abs_start + p,
                chunk_end=abs_start + p + chosen_n - 1,
            )
        )
        p += chosen_n

    return pieces


def split_large_record_without_llm(
    source_texts: List[str],
    abs_start: int,
    token_cap: int,
    max_window: int,
) -> List[Piece]:
    pieces: List[Piece] = []
    p = 0
    n_total = len(source_texts)

    while p < n_total:
        first = source_texts[p]
        first_tok = estimate_tokens(first)
        if first_tok > token_cap:
            subs = split_single_text(first, token_cap=token_cap)
            for sub in subs:
                pieces.append(Piece(text=sub, chunk_start=abs_start + p, chunk_end=abs_start + p))
            p += 1
            continue

        cur_texts = [first]
        cur_tokens = first_tok
        q = p + 1
        while q < n_total and (q - p) < max_window:
            nxt = source_texts[q]
            nt = estimate_tokens(nxt)
            if cur_tokens + nt > token_cap:
                break
            cur_texts.append(nxt)
            cur_tokens += nt
            q += 1

        pieces.append(
            Piece(
                text="\n".join(cur_texts).strip(),
                chunk_start=abs_start + p,
                chunk_end=abs_start + q - 1,
            )
        )
        p = q

    return pieces


def regen_questions_summary(
    rec: Dict[str, Any],
    client: Any,
    controller: Any,
    model: str,
) -> Dict[str, Any]:
    text = str(rec.get("output") or "")
    if not text.strip():
        rec["input"] = ""
        rec["summary"] = ""
        rec["alt_question_1"] = ""
        rec["alt_question_2"] = ""
        rec["alt_question_3"] = ""
        return rec

    q_prompt = build_questions_prompt(text=text, num_questions=3)
    q_raw = safe_chat_completion(
        client=client,
        controller=controller,
        model=model,
        prompt_text=q_prompt,
        max_tokens=256,
        temperature=0.2,
        call_label="stage5_regen_question",
        call_meta={
            "source_file": rec.get("source_file", ""),
            "chunk_start": rec.get("chunk_start", ""),
            "chunk_end": rec.get("chunk_end", ""),
            "resplit_part_index": rec.get("resplit_part_index", ""),
            "resplit_part_count": rec.get("resplit_part_count", ""),
            "parent_chunk_id": rec.get("resplit_parent_chunk_id", ""),
        },
    )
    candidates = extract_scored_question_candidates(q_raw)
    questions = [q for _, q in candidates][:3]

    rec["input"] = questions[0] if questions else ""
    rec["alt_question_1"] = questions[1] if len(questions) > 1 else ""
    rec["alt_question_2"] = questions[2] if len(questions) > 2 else ""
    rec["alt_question_3"] = ""

    s_prompt = build_summary_prompt(
        text=text,
        book_title=str(rec.get("source_title") or ""),
        chapter_title="",
        section_title="",
        section_path="",
        prev_heading="",
        next_heading="",
    )
    s_raw = safe_chat_completion(
        client=client,
        controller=controller,
        model=model,
        prompt_text=s_prompt,
        max_tokens=320,
        temperature=0.2,
        call_label="stage5_regen_summary",
        call_meta={
            "source_file": rec.get("source_file", ""),
            "chunk_start": rec.get("chunk_start", ""),
            "chunk_end": rec.get("chunk_end", ""),
            "resplit_part_index": rec.get("resplit_part_index", ""),
            "resplit_part_count": rec.get("resplit_part_count", ""),
            "parent_chunk_id": rec.get("resplit_parent_chunk_id", ""),
        },
    )
    rec["summary"] = extract_summary(s_raw)
    return rec


def resolve_source_json_path(index_dir: str, source_file: str) -> Optional[str]:
    if not source_file:
        return None
    if os.path.isabs(source_file):
        return source_file if os.path.exists(source_file) else None
    candidate = os.path.join(index_dir, source_file)
    if os.path.exists(candidate):
        return candidate
    return None


def load_source_chunks(source_json_path: str) -> List[str]:
    payload = load_json(source_json_path)
    if not isinstance(payload, list):
        return []
    out: List[str] = []
    for row in payload:
        if isinstance(row, dict):
            out.append(str(row.get("output") or ""))
    return out


def reindex_records(records: List[Dict[str, Any]]) -> None:
    if not records:
        return
    doc_id = str(records[0].get("doc_id") or "")
    count = len(records)
    for i, rec in enumerate(records, start=1):
        rec["chunk_index"] = i
        rec["chunk_count"] = count
        rec["semantic_block_index"] = i
        if doc_id:
            rec["doc_id"] = doc_id
            rec["chunk_id"] = f"{doc_id}:chunk_{i:05d}"
            rec["prev_chunk_id"] = f"{doc_id}:chunk_{i-1:05d}" if i > 1 else ""
            rec["next_chunk_id"] = f"{doc_id}:chunk_{i+1:05d}" if i < count else ""


def derive_output_path(ingest_path: str, in_place: bool) -> str:
    if in_place:
        return ingest_path
    if ingest_path.endswith("_semantic_ingest.json"):
        return ingest_path.replace("_semantic_ingest.json", "_semantic_ingest_resplit.json")
    base, ext = os.path.splitext(ingest_path)
    if not ext:
        ext = ".json"
    return f"{base}_resplit{ext}"


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


def initialize_status(
    ingest_path: str,
    out_path: str,
    payload: List[Dict[str, Any]],
    token_cap: int,
    max_window: int,
) -> Dict[str, Any]:
    return {
        "version": 1,
        "started_at": now_iso(),
        "updated_at": now_iso(),
        "ingest_path": ingest_path,
        "output_path": out_path,
        "ingest_file_signature": file_signature(ingest_path),
        "ingest_payload_signature": payload_signature(payload),
        "token_cap": token_cap,
        "max_window": max_window,
        "phase": "split",
        "split_next_source_index": 0,
        "regen_next_changed_pos": 0,
        "oversized_before": 0,
        "changed_indices": [],
        "done": False,
    }


def status_is_compatible(
    status: Dict[str, Any],
    ingest_path: str,
    payload: List[Dict[str, Any]],
    token_cap: int,
    max_window: int,
) -> bool:
    try:
        if str(status.get("ingest_path", "")) != ingest_path:
            return False
        if int(status.get("token_cap", -1)) != int(token_cap):
            return False
        if int(status.get("max_window", -1)) != int(max_window):
            return False
        sig_a = status.get("ingest_file_signature") or {}
        sig_b = file_signature(ingest_path)
        if int(sig_a.get("size", -1)) != int(sig_b.get("size", -2)):
            return False
        if int(sig_a.get("mtime_ns", -1)) != int(sig_b.get("mtime_ns", -2)):
            return False
        pay_a = status.get("ingest_payload_signature") or {}
        pay_b = payload_signature(payload)
        if str(pay_a.get("sha1", "")) != str(pay_b.get("sha1", "__mismatch__")):
            return False
        return True
    except Exception:
        return False


def process_file(
    ingest_path: str,
    index_dir: str,
    token_cap: int,
    max_window: int,
    client: Any,
    controller: Any,
    model: str,
    dry_run: bool,
    in_place: bool,
    resume: bool,
) -> Dict[str, Any]:
    payload = load_json(ingest_path)
    if not isinstance(payload, list):
        return {"file": ingest_path, "status": "skip_not_list"}

    out_path = derive_output_path(ingest_path=ingest_path, in_place=in_place)
    status_path = out_path + ".stage5_status.json"
    work_path = out_path + ".stage5_work.json"

    source_cache: Dict[str, List[str]] = {}
    output_records: List[Dict[str, Any]] = []
    status: Dict[str, Any]

    if (not dry_run) and resume and os.path.exists(status_path) and os.path.exists(work_path):
        try:
            loaded_status = load_json(status_path)
            loaded_work = load_json(work_path)
            if isinstance(loaded_status, dict) and isinstance(loaded_work, list) and status_is_compatible(
                loaded_status, ingest_path, payload, token_cap, max_window
            ):
                status = loaded_status
                output_records = loaded_work
                print(
                    f"[RESUME] file={ingest_path} phase={status.get('phase')} "
                    f"split_next={status.get('split_next_source_index', 0)} "
                    f"regen_pos={status.get('regen_next_changed_pos', 0)}"
                )
            else:
                status = initialize_status(ingest_path, out_path, payload, token_cap, max_window)
                output_records = []
        except Exception:
            status = initialize_status(ingest_path, out_path, payload, token_cap, max_window)
            output_records = []
    else:
        status = initialize_status(ingest_path, out_path, payload, token_cap, max_window)
        output_records = []

    if status.get("done") and os.path.exists(out_path):
        return {
            "file": ingest_path,
            "status": "already_done",
            "output_file": out_path,
            "oversized_before": int(status.get("oversized_before", 0)),
            "oversized_after": int(status.get("oversized_after", 0)),
            "rows_before": len(payload),
            "rows_after": int(status.get("rows_after", 0)),
            "rows_regenerated": int(status.get("rows_regenerated", 0)),
        }

    def fail_and_persist(phase: str, context: Dict[str, Any], exc: Exception) -> Dict[str, Any]:
        status["done"] = False
        status["phase"] = phase
        status["failed"] = True
        status["failed_at"] = now_iso()
        status["last_error"] = str(exc)
        status["last_error_context"] = context
        status["updated_at"] = now_iso()
        if not dry_run:
            atomic_save_json(work_path, output_records)
            atomic_save_json(status_path, status)
        return {
            "file": ingest_path,
            "status": "failed",
            "phase": phase,
            "output_file": out_path,
            "oversized_before": int(status.get("oversized_before", 0)),
            "rows_before": len(payload),
            "rows_after": len(output_records),
            "error": str(exc),
            "error_context": context,
        }

    # Phase 1: split oversized records (checkpointed per source index).
    split_next = int(status.get("split_next_source_index", 0))
    oversized_before = int(status.get("oversized_before", 0))

    if status.get("phase") in ("split", None):
        for src_idx in range(split_next, len(payload)):
            rec = payload[src_idx]
            if not isinstance(rec, dict):
                status["split_next_source_index"] = src_idx + 1
                continue

            try:
                out_text = str(rec.get("output") or "")
                out_tokens = estimate_tokens(out_text)
                if out_tokens <= token_cap:
                    kept = dict(rec)
                    kept.setdefault("resplit_applied", False)
                    kept.setdefault("resplit_method", "")
                    output_records.append(kept)
                else:
                    oversized_before += 1

                    parent_chunk_id = str(rec.get("chunk_id") or "")
                    parent_chunk_index = int(rec.get("chunk_index") or 0)
                    chunk_start = int(rec.get("chunk_start") or 0)
                    chunk_end = int(rec.get("chunk_end") or chunk_start)
                    if chunk_start <= 0:
                        chunk_start = int(rec.get("chunk_index") or 1)
                    if chunk_end < chunk_start:
                        chunk_end = chunk_start

                    source_file = str(rec.get("source_file") or "")
                    source_path = resolve_source_json_path(index_dir, source_file)
                    source_chunks: List[str] = []
                    if source_path:
                        if source_path not in source_cache:
                            source_cache[source_path] = load_source_chunks(source_path)
                        source_chunks = source_cache[source_path]

                    if source_chunks and chunk_end <= len(source_chunks):
                        segment = source_chunks[chunk_start - 1 : chunk_end]
                        if dry_run or client is None or controller is None or not model:
                            pieces = split_large_record_without_llm(
                                source_texts=segment,
                                abs_start=chunk_start,
                                token_cap=token_cap,
                                max_window=max_window,
                            )
                        else:
                            pieces = split_large_record_with_llm(
                                source_texts=segment,
                                abs_start=chunk_start,
                                token_cap=token_cap,
                                max_window=max_window,
                                client=client,
                                controller=controller,
                                model=model,
                                parent_chunk_id=parent_chunk_id,
                                source_file=source_file,
                            )
                    else:
                        fallback_pieces = split_single_text(out_text, token_cap=token_cap)
                        pieces = [
                            Piece(text=t, chunk_start=chunk_start, chunk_end=chunk_end)
                            for t in fallback_pieces
                        ]
                    if not pieces:
                        raise RuntimeError("Split produced zero pieces.")

                    part_count = len(pieces)
                    for part_idx, piece in enumerate(pieces, start=1):
                        new_rec = dict(rec)
                        new_rec["output"] = piece.text
                        new_rec["chunk_start"] = piece.chunk_start
                        new_rec["chunk_end"] = piece.chunk_end
                        new_rec["input"] = ""
                        new_rec["summary"] = ""
                        new_rec["alt_question_1"] = ""
                        new_rec["alt_question_2"] = ""
                        new_rec["alt_question_3"] = ""
                        new_rec["resplit_applied"] = True
                        new_rec["resplit_method"] = "stage5_semantic_resplit_v1"
                        new_rec["resplit_at"] = now_iso()
                        new_rec["resplit_parent_chunk_id"] = parent_chunk_id
                        new_rec["resplit_parent_chunk_index"] = parent_chunk_index
                        new_rec["resplit_parent_chunk_start"] = chunk_start
                        new_rec["resplit_parent_chunk_end"] = chunk_end
                        new_rec["resplit_part_index"] = part_idx
                        new_rec["resplit_part_count"] = part_count
                        output_records.append(new_rec)
            except Exception as exc:
                return fail_and_persist(
                    phase="split",
                    context={
                        "step": "split_record",
                        "source_index": src_idx,
                        "source_file": rec.get("source_file"),
                        "chunk_start": rec.get("chunk_start"),
                        "chunk_end": rec.get("chunk_end"),
                        "chunk_id": rec.get("chunk_id"),
                    },
                    exc=exc,
                )

            status["split_next_source_index"] = src_idx + 1
            status["oversized_before"] = oversized_before
            status["updated_at"] = now_iso()
            if not dry_run:
                atomic_save_json(work_path, output_records)
                atomic_save_json(status_path, status)
        status["phase"] = "regen"
        status["regen_next_changed_pos"] = int(status.get("regen_next_changed_pos", 0))
        status["updated_at"] = now_iso()
        reindex_records(output_records)
        if not dry_run:
            atomic_save_json(work_path, output_records)
            atomic_save_json(status_path, status)

    changed_indices = [i for i, rec in enumerate(output_records) if bool(rec.get("resplit_applied"))]
    status["changed_indices"] = changed_indices

    if not changed_indices:
        status["done"] = True
        status["phase"] = "done"
        status["oversized_after"] = 0
        status["rows_after"] = len(output_records)
        status["rows_regenerated"] = 0
        status["completed_at"] = now_iso()
        status["updated_at"] = now_iso()
        if not dry_run:
            atomic_save_json(status_path, status)
        return {"file": ingest_path, "status": "no_oversized", "oversized_before": oversized_before}

    # Phase 2: regenerate Q/S for changed rows (checkpointed per changed index).
    if not dry_run:
        regen_pos = int(status.get("regen_next_changed_pos", 0))
        for pos in range(regen_pos, len(changed_indices)):
            idx = changed_indices[pos]
            try:
                output_records[idx] = regen_questions_summary(
                    rec=output_records[idx],
                    client=client,
                    controller=controller,
                    model=model,
                )
            except Exception as exc:
                return fail_and_persist(
                    phase="regen",
                    context={
                        "step": "regen_questions_summary",
                        "changed_pos": pos,
                        "record_index": idx,
                        "chunk_start": output_records[idx].get("chunk_start"),
                        "chunk_end": output_records[idx].get("chunk_end"),
                        "source_file": output_records[idx].get("source_file"),
                        "parent_chunk_id": output_records[idx].get("resplit_parent_chunk_id", ""),
                        "part_index": output_records[idx].get("resplit_part_index", ""),
                        "part_count": output_records[idx].get("resplit_part_count", ""),
                    },
                    exc=exc,
                )
            status["regen_next_changed_pos"] = pos + 1
            status["updated_at"] = now_iso()
            atomic_save_json(work_path, output_records)
            atomic_save_json(status_path, status)

    oversized_after = sum(1 for r in output_records if estimate_tokens(str(r.get("output") or "")) > token_cap)

    if not dry_run:
        if in_place:
            ts = datetime.now().strftime("%Y%m%d%H%M%S")
            backup = ingest_path.replace(".json", f".bak_stage5_{ts}.json")
            atomic_save_json(backup, payload)
        atomic_save_json(out_path, output_records)

        status["done"] = True
        status["phase"] = "done"
        status["oversized_after"] = oversized_after
        status["rows_after"] = len(output_records)
        status["rows_regenerated"] = len(changed_indices)
        status["completed_at"] = now_iso()
        status["updated_at"] = now_iso()
        atomic_save_json(status_path, status)

    return {
        "file": ingest_path,
        "status": "updated",
        "output_file": out_path,
        "oversized_before": oversized_before,
        "oversized_after": oversized_after,
        "rows_before": len(payload),
        "rows_after": len(output_records),
        "rows_regenerated": len(changed_indices),
    }


def discover_ingest_files(index_dir: str, pattern: str) -> List[str]:
    if os.path.isabs(pattern):
        return sorted([p for p in glob.glob(pattern) if os.path.isfile(p)])
    return sorted(
        [p for p in glob.glob(os.path.join(index_dir, pattern)) if os.path.isfile(p)]
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stage-5 pass: resplit oversized semantic ingest records and regenerate questions/summaries."
    )
    parser.add_argument("--index-dir", default="securitybooks")
    parser.add_argument("--pattern", default="*_semantic_ingest.json")
    parser.add_argument("--config", default="", help="Runtime config JSON (default: postprocess_config.json fallback).")
    parser.add_argument("--max-output-tokens", type=int, default=4096)
    parser.add_argument("--max-window", type=int, default=24)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--in-place", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-resume", action="store_true", help="Disable resume/checkpoint and start each file from scratch.")
    parser.add_argument("--summary-file", default="")
    args = parser.parse_args()

    index_dir = os.path.abspath(args.index_dir)
    files = discover_ingest_files(index_dir=index_dir, pattern=args.pattern)
    if args.max_files > 0:
        files = files[: args.max_files]

    if not files:
        print(f"[INFO] No files found under {index_dir} matching {args.pattern}")
        return

    config = load_runtime_config(args.config or None)
    if args.dry_run:
        client = None
        model = ""
        controller = None
    else:
        client, model, _, controller = create_client_from_config(config)

    print(f"[INFO] Stage-5 start at {now_iso()}")
    print(f"[INFO] index_dir={index_dir}")
    print(f"[INFO] files={len(files)} token_cap={args.max_output_tokens} max_window={args.max_window}")
    if args.dry_run:
        print("[INFO] dry-run enabled: no API calls, no writes")

    results: List[Dict[str, Any]] = []
    for path in files:
        print(f"[FILE] {path}")
        res = process_file(
            ingest_path=path,
            index_dir=index_dir,
            token_cap=max(256, int(args.max_output_tokens)),
            max_window=max(2, int(args.max_window)),
            client=client,
            controller=controller,
            model=model,
            dry_run=args.dry_run,
            in_place=args.in_place,
            resume=(not args.no_resume),
        )
        results.append(res)
        print(f"[RESULT] {res}")

    summary = {
        "started_at": now_iso(),
        "index_dir": index_dir,
        "token_cap": args.max_output_tokens,
        "dry_run": args.dry_run,
        "in_place": args.in_place,
        "total_files": len(files),
        "updated_files": sum(1 for r in results if r.get("status") == "updated"),
        "results": results,
    }
    if args.summary_file:
        save_json(args.summary_file, summary)
        print(f"[SUMMARY] wrote {args.summary_file}")
    else:
        print("[SUMMARY]")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
