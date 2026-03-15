#!/usr/bin/env python3
import argparse
import glob
import json
import os
from datetime import datetime, timezone

from postprocess_llm_common import (
    load_runtime_config,
    create_client_from_config,
    safe_chat_completion,
    strip_think_tags,
)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_yes_no(raw: str) -> bool:
    text = strip_think_tags(raw or "").strip().lower()
    if not text:
        return True
    if "yes" in text and "no" in text:
        return text.index("yes") < text.index("no")
    if "yes" in text:
        return True
    if "no" in text:
        return False
    return True


def build_prompt(text: str) -> str:
    snippet = (text or "").strip()
    return (
        "You are classifying one extracted block from a book for RAG ingestion.\n\n"
        "Return exactly one token: yes or no\n"
        "- yes = keep as book content\n"
        "- no = drop as non-content/noise\n\n"
        "Classify as no when the block is primarily:\n"
        "- table of contents / chapter listings / dot-leader page lists\n"
        "- back-of-book index entries (term + page numbers)\n"
        "- publisher/copyright/ISBN/customer-care/ordering/legal notices\n"
        "- acknowledgements, dedication, foreword/preface, about-the-author, ads\n"
        "- glossary/bibliography/reference lists with little explanatory prose\n"
        "- navigation-only text or mostly metadata rather than instructional/explanatory content\n\n"
        "Classify as yes when the block contains substantive instructional, technical, or conceptual material,\n"
        "including examples, explanations, walkthroughs, case studies, commands, code, or mitigation guidance.\n\n"
        "Important distinction:\n"
        "- A chapter opener with heading markers (for example 'Chapter X', 'In This Chapter', bullets) is still yes\n"
        "  if the block includes meaningful explanatory prose after the heading.\n"
        "- Do not mark as no solely because the block begins with a chapter title or section heading.\n\n"
        "Strong yes signals:\n"
        "- narrative paragraphs explaining how/why something works\n"
        "- technical discussion of vulnerabilities, protocols, attacks, defenses, tools, or procedures\n"
        "- actionable guidance, steps, or interpretation\n\n"
        "Strong no signals:\n"
        "- mostly lists of terms + page numbers\n"
        "- comma-separated keyword fragments followed by many page numbers/ranges\n"
        "- appendix/resource listings that are primarily names/URLs/tool lists without explanation\n"
        "- mostly publication/legal/contact info\n"
        "- mostly navigation structures without explanation\n\n"
        "If a block has one short heading-like phrase but is otherwise dominated by index-style entries\n"
        "(many numbers, ranges, comma-separated terms), classify as no.\n\n"
        "Tie-break rule:\n"
        "- If unsure, prefer yes when there is any meaningful explanatory prose.\n"
        "- Prefer no only when the block is predominantly navigational/listing/metadata text.\n\n"
        "Output only: yes or no\n\n"
        "Text snippet:\n"
        f"{snippet}\n"
    )


def is_trueish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return True


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


def main():
    parser = argparse.ArgumentParser(description="Post-process semantic work files to classify non-book-content blocks.")
    parser.add_argument("--config", default="", help="Path to runtime config JSON (default: postprocess_config.json).")
    parser.add_argument("--pattern", default="securitybooks/.semantic_work/*_semantic_work.json")
    parser.add_argument("--in-place", action="store_true", help="Modify files in place (default writes *_filtered.json).")
    parser.add_argument("--status-file", default="securitybooks/.semantic_work/.post_filter_status.json")
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--max-blocks-per-file", type=int, default=0)
    parser.add_argument("--skip-currently-active", action="store_true", help="Skip file if mtime changed in last 60s.")
    args = parser.parse_args()

    config = load_runtime_config(args.config or None)
    client, model, _, controller = create_client_from_config(config)

    files = sorted(glob.glob(args.pattern))
    if args.max_files > 0:
        files = files[: args.max_files]

    status = load_status(args.status_file)
    total_updates = 0

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

        file_state = status["files"].setdefault(path, {"done_indices": [], "updated": 0})
        done = set(file_state.get("done_indices") or [])

        changed = 0
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

            text = str(block.get("text") or "")

            # If block is already false, keep as-is but mark done.
            if not is_trueish(block.get("is_book_content", True)):
                done.add(idx)
                continue

            prompt = build_prompt(text)
            raw = safe_chat_completion(
                client=client,
                controller=controller,
                model=model,
                prompt_text=prompt,
                max_tokens=int(config.get("ContentCheckMaxTokens") or 128),
                temperature=0.0,
            )
            keep = parse_yes_no(raw)
            block["is_book_content"] = bool(keep)
            done.add(idx)
            if not keep:
                changed += 1
            print(f"[FILTER] idx={idx+1}/{len(blocks)} keep={keep}")

            file_state["done_indices"] = sorted(done)
            file_state["updated"] = int(file_state.get("updated", 0)) + (0 if keep else 1)
            save_status(args.status_file, status)

        out_path = path if args.in_place else path.replace("_semantic_work.json", "_semantic_work_filtered.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)

        total_updates += changed
        print(f"[DONE] {path} changed_non_content={changed} output={out_path}")

    status["finished_at"] = now_iso()
    status["total_non_content_updates"] = total_updates
    save_status(args.status_file, status)
    print(f"[SUMMARY] total_non_content_updates={total_updates}")


if __name__ == "__main__":
    main()
