#!/usr/bin/env python3
import argparse
import glob
import json
import os
import re
from datetime import datetime, timezone

from postprocess_llm_common import (
    load_runtime_config,
    create_client_from_config,
    safe_chat_completion,
    strip_think_tags,
)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_status(path: str):
    if not os.path.exists(path):
        return {"started_at": now_iso(), "files": {}}
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        payload = {"started_at": now_iso(), "files": {}}
    payload.setdefault("files", {})
    return payload


def save_status(path: str, status: dict):
    status["updated_at"] = now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def extract_summary(raw: str) -> str:
    text = strip_think_tags(raw or "")
    m = re.search(r"(?is)<summary>\s*(.*?)\s*</summary>", text)
    if m:
        text = m.group(1)
    text = re.sub(r"\s+", " ", text).strip().strip('"\'')
    return text


def is_trueish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return True


def build_prompt(
    text: str,
    book_title: str = "",
    chapter_title: str = "",
    section_title: str = "",
    section_path: str = "",
    prev_heading: str = "",
    next_heading: str = "",
) -> str:
    chunk = (text or "").strip()
    return (
        "You are writing retrieval-routing synopses for chunked technical books.\n\n"
        "Purpose of this output:\n"
        "- The raw chunk text is stored separately and remains the primary evidence.\n"
        "- Your output is secondary routing metadata used to help retrieval find the right chunk and distinguish it from nearby chunks on similar topics.\n"
        "- Retrieval uses both semantic matching and lexical/BM25 matching.\n"
        "- The document collection is hierarchical, so specificity and disambiguation matter.\n\n"
        "Task:\n"
        "Write exactly ONE retrieval-routing synopsis for the chunk below.\n\n"
        "What the synopsis must do:\n"
        "- Capture the chunk's main technical subject and the most distinctive details that help retrieve it.\n"
        "- Preserve exact retrieval anchors naturally when useful: CVEs, versions, RFCs, protocols, APIs, functions, classes, commands, flags, filenames, config keys, ports, products, tools, libraries, and diagnostic error strings.\n"
        "- State the key mechanism, action, failure mode, exploit path, mitigation, prerequisite, comparison, dependency, or outcome only when it is actually present in the chunk.\n"
        "- Make this chunk distinguishable from adjacent chunks on related topics.\n"
        "- Complement retrieval questions by expressing the chunk's technical identity, not by generating questions or paraphrasing likely user queries.\n\n"
        "Grounding rules:\n"
        "- Every claim must be directly supported by the chunk text.\n"
        "- Stay scoped to this exact chunk, not the whole chapter or book.\n"
        "- Use metadata only to resolve naming or scope; never use it to add facts not supported by the chunk.\n"
        "- Never invent entities, versions, causes, effects, fixes, examples, or surrounding context.\n"
        "- Do not omit exact tokens that are likely to matter for retrieval.\n\n"
        "Style rules:\n"
        "- Write 1 dense sentence if possible; use 2 sentences only if needed.\n"
        "- Target 35 to 80 words total.\n"
        "- Start with the dominant subject, component, tool, protocol, vulnerability, API, or mechanism when possible.\n"
        "- Use explicit nouns, not vague pronouns.\n"
        "- Sound like precise technical prose, not an educational abstract.\n"
        "- Include exact anchors naturally; do not keyword-stuff.\n"
        "- Preserve code/config/log tokens when they are the main retrieval signal.\n"
        "- Do not say 'this section', 'the text', 'the passage', 'the snippet', 'the chapter', or 'described here'.\n"
        "- Do not write a title, list, commentary, explanation, or markdown.\n\n"
        "Special handling:\n"
        "- If the chunk is procedural, include action + target + intended result.\n"
        "- If the chunk is security-focused, include affected component + technique or precondition + impact or mitigation when present.\n"
        "- If the chunk is code, config, logs, or command output, summarize what it does or shows and preserve the most searchable exact tokens.\n"
        "- If the chunk is fragmented or narrow, still produce the most specific grounded synopsis possible rather than a generic abstract.\n\n"
        "Avoid weak outputs such as:\n"
        "- 'This section discusses networking concepts and security tools.'\n"
        "- 'The text explains an important idea related to APIs.'\n"
        "- 'The passage covers techniques, commands, and best practices.'\n\n"
        "Silent quality check before answering:\n"
        "1. Would this synopsis help distinguish this chunk from nearby chunks?\n"
        "2. Did I preserve the chunk's most important exact anchors?\n"
        "3. Is every claim directly supported by the chunk?\n"
        "4. Would a plausible user query overlap with this wording?\n"
        "If any answer is no, revise before replying.\n\n"
        "Output format:\n"
        "Return only:\n"
        "<summary>...</summary>\n\n"
        "Metadata (for disambiguation only):\n"
        f"Book title: {book_title or '[unknown]'}\n"
        f"Chapter title: {chapter_title or '[unknown]'}\n"
        f"Section title: {section_title or '[unknown]'}\n"
        f"Section path: {section_path or '[unknown]'}\n"
        f"Previous heading: {prev_heading or '[unknown]'}\n"
        f"Next heading: {next_heading or '[unknown]'}\n\n"
        f"Chunk text:\n<<<\n{chunk}\n>>>\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Improve summary quality in semantic work files.")
    parser.add_argument("--config", default="", help="Path to runtime config JSON (default: postprocess_config.json).")
    parser.add_argument("--pattern", default="securitybooks/.semantic_work/*_semantic_work.json")
    parser.add_argument("--in-place", action="store_true", help="Modify files in place (default writes *_sv2.json).")
    parser.add_argument("--status-file", default="securitybooks/.semantic_work/.post_summaries_status.json")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-blocks-per-file", type=int, default=0)
    parser.add_argument("--skip-currently-active", action="store_true")
    args = parser.parse_args()

    config = load_runtime_config(args.config or None)
    client, model, _, controller = create_client_from_config(config)

    files = sorted(glob.glob(args.pattern))
    if args.max_files > 0:
        files = files[: args.max_files]

    status = load_status(args.status_file)
    total_replaced = 0

    for path in files:
        if not os.path.isfile(path):
            continue
        if args.skip_currently_active:
            age = max(0.0, datetime.now().timestamp() - os.path.getmtime(path))
            if age < 60:
                print(f"[SKIP] Recently modified (likely active): {path}")
                continue

        print(f"[FILE] {path}")
        with open(path, "r", encoding="utf-8") as f:
            blocks = json.load(f)
        if not isinstance(blocks, list):
            print(f"[WARN] Not a JSON list: {path}")
            continue

        file_state = status["files"].setdefault(path, {"done_indices": [], "replaced": 0})
        done = set(file_state.get("done_indices") or [])

        replaced = 0
        processed = 0
        for idx, block in enumerate(blocks):
            if idx in done:
                continue
            if args.max_blocks_per_file > 0 and processed >= args.max_blocks_per_file:
                break
            processed += 1

            if not isinstance(block, dict):
                done.add(idx)
                continue
            if not is_trueish(block.get("is_book_content", True)):
                done.add(idx)
                continue

            text = str(block.get("text") or "")
            prompt = build_prompt(
                text=text,
                book_title=str(block.get("source_title") or block.get("book_title") or ""),
                chapter_title=str(block.get("chapter_title") or ""),
                section_title=str(block.get("section_title") or ""),
                section_path=str(block.get("section_path") or ""),
                prev_heading=str(block.get("prev_heading") or ""),
                next_heading=str(block.get("next_heading") or ""),
            )

            raw = safe_chat_completion(
                client=client,
                controller=controller,
                model=model,
                prompt_text=prompt,
                max_tokens=320,
                temperature=0.2,
            )
            new_s = extract_summary(raw)
            use_new = bool(new_s)
            if use_new:
                block["summary"] = new_s
                replaced += 1
            done.add(idx)
            print(f"[S] idx={idx+1}/{len(blocks)} replaced={use_new}")

            file_state["done_indices"] = sorted(done)
            file_state["replaced"] = int(file_state.get("replaced", 0)) + (1 if use_new else 0)
            save_status(args.status_file, status)

        out_path = path if args.in_place else path.replace("_semantic_work.json", "_semantic_work_sv2.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)

        total_replaced += replaced
        print(f"[DONE] {path} replaced_summaries={replaced} output={out_path}")

    status["finished_at"] = now_iso()
    status["total_summaries_replaced"] = total_replaced
    save_status(args.status_file, status)
    print(f"[SUMMARY] total_summaries_replaced={total_replaced}")


if __name__ == "__main__":
    main()
