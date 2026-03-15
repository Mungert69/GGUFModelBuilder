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


def extract_question(raw: str) -> str:
    text = strip_think_tags(raw or "")
    m = re.search(r"(?is)<question>\s*(.*?)\s*</question>", text)
    if m:
        text = m.group(1)
    text = re.sub(r"\s+", " ", text).strip().strip('"\'')
    return text


def extract_questions(raw: str) -> tuple[str, list[str]]:
    text = strip_think_tags(raw or "")
    primary = ""
    alternates: list[str] = []

    m = re.search(r"(?is)<question>\s*(.*?)\s*</question>", text)
    if m:
        primary = re.sub(r"\s+", " ", m.group(1)).strip().strip('"\'')

    alts_block = re.search(r"(?is)<alt_questions>\s*(.*?)\s*</alt_questions>", text)
    if alts_block:
        block = alts_block.group(1)
        for alt in re.findall(r"(?is)<alt>\s*(.*?)\s*</alt>", block):
            q = re.sub(r"\s+", " ", alt).strip().strip('"\'')
            if q and q.lower() != primary.lower():
                alternates.append(q)

    # Fallback: if tags are missing, use legacy parser for primary.
    if not primary:
        primary = extract_question(text)

    # Deduplicate while preserving order and cap at 2.
    seen = set()
    clean_alts = []
    for q in alternates:
        k = q.lower()
        if k in seen:
            continue
        seen.add(k)
        clean_alts.append(q)
        if len(clean_alts) >= 2:
            break
    return primary, clean_alts


def extract_scored_question_candidates(raw: str) -> list[tuple[float, str]]:
    text = strip_think_tags(raw or "")
    candidates: list[tuple[float, str]] = []

    # Preferred structured format.
    m = re.search(r"(?is)<questions>\s*(.*?)\s*</questions>", text)
    if m:
        block = m.group(1)
        for q_match in re.finditer(r"(?is)<q(?:\s+score=\"([0-9]+(?:\.[0-9]+)?)\")?\s*>(.*?)\s*</q>", block):
            score_str = q_match.group(1)
            q = q_match.group(2)
            cleaned = re.sub(r"\s+", " ", q).strip().strip('"\'')
            if not cleaned:
                continue
            score = 0.0
            if score_str:
                try:
                    score = float(score_str)
                except ValueError:
                    score = 0.0
            candidates.append((score, cleaned))

    # Fallback to previous format support.
    if not candidates:
        primary, alts = extract_questions(text)
        if primary:
            candidates.append((0.0, primary))
        for q in alts:
            candidates.append((0.0, q))

    # Dedup preserve order, keep max score if duplicates appear.
    merged = {}
    order = []
    for score, q in candidates:
        k = q.lower()
        if k not in merged:
            merged[k] = (score, q)
            order.append(k)
        else:
            prev_score, prev_q = merged[k]
            if score > prev_score:
                merged[k] = (score, prev_q)

    deduped = [merged[k] for k in order]

    # If model provided scores, sort descending by score.
    has_any_score = any(score > 0 for score, _ in deduped)
    if has_any_score:
        deduped.sort(key=lambda x: x[0], reverse=True)
    return deduped[:3]


def is_trueish(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return True


def build_prompt(text: str, num_questions: int = 3) -> str:
    snippet = (text or "").strip()
    return (
        "You are generating index-time retrieval questions for a hybrid RAG system over technical books.\n\n"
        "Your job is to create high-utility questions that real users might ask when the answer is contained in the given chunk.\n\n"
        "These are retrieval anchors, not study questions, not summaries, not flashcards, and not chapter-wide discussion prompts.\n\n"
        "Retrieval setting:\n"
        "- The original chunk text is indexed separately.\n"
        "- Your questions are additional retrieval views tied to the same chunk.\n"
        "- Retrieval uses both:\n"
        "  1) semantic vector search\n"
        "  2) lexical/BM25 matching\n\n"
        "Therefore, your questions must help both retrieval modes:\n"
        "- Some questions should preserve exact technical terms for lexical matching.\n"
        "- Some questions should paraphrase naturally for semantic matching.\n\n"
        "Primary objective:\n"
        f"Generate exactly {num_questions} distinct, content-grounded questions that improve retrieval precision and recall for this exact chunk.\n\n"
        "Grounding rules:\n"
        "- Every question must be answerable from the chunk text itself.\n"
        "- Use document metadata only to disambiguate wording, never to introduce facts not supported by the chunk.\n"
        "- Reuse exact entities when useful:\n"
        "  protocol names, CVEs, RFCs, versions, APIs, functions, classes, commands, flags, filenames, config keys, ports, error messages, standards, products, tools, libraries, and environment names.\n"
        "- Never invent entities, versions, commands, file paths, causes, mitigations, or relationships not present in the chunk.\n"
        "- Do not broaden the question to the whole book, whole chapter, or adjacent sections.\n\n"
        "Coverage and diversity:\n"
        "Generate questions that cover distinct retrievable angles actually present in the chunk, such as:\n"
        "- definition or identification\n"
        "- mechanism or behavior\n"
        "- procedure or step\n"
        "- troubleshooting or failure mode\n"
        "- mitigation or best practice\n"
        "- comparison or dependency\n"
        "- prerequisite, constraint, or version-specific behavior\n"
        "- exact entity / command / API / error lookup\n\n"
        "Only use angles supported by the chunk.\n"
        "Do not produce near-duplicates or shallow rephrasings.\n\n"
        "Balance requirements:\n"
        "- At least 2 questions should preserve exact lexical anchors from the chunk.\n"
        "- At least 2 questions should use natural semantic paraphrase.\n"
        "- If the chunk contains commands, code, config, logs, CVEs, versions, RFCs, flags, or error strings, at least 1 question should preserve those exact tokens.\n"
        "- If the chunk contains a mitigation, exploit path, failure condition, or prerequisite, cover it directly.\n\n"
        "Style rules:\n"
        "- One sentence per question.\n"
        "- End each question with \"?\".\n"
        "- Use standalone wording with explicit nouns instead of vague pronouns.\n"
        "- Make questions sound like realistic user searches.\n"
        "- Keep each question faithful to the chunk's scope.\n"
        "- Avoid generic prompts such as:\n"
        "  \"What are the key points of X?\"\n"
        "  \"Why is X important?\"\n"
        "  \"What does this section discuss?\"\n"
        "- Do not use phrases like:\n"
        "  \"according to the text\"\n"
        "  \"in this section\"\n"
        "  \"described here\"\n"
        "  \"mentioned above\"\n\n"
        "Quality filter:\n"
        "Before producing the final output, silently remove any question that is:\n"
        "- not answerable from the chunk\n"
        "- too broad\n"
        "- too narrow to help retrieval\n"
        "- redundant with another question\n"
        "- based on invented or weakly implied details\n\n"
        "Ordering:\n"
        "Order questions by expected retrieval usefulness for this exact chunk, best first.\n\n"
        "Output format:\n"
        "Return only this XML and nothing else:\n\n"
        "<questions>\n"
        "  <q score=\"0-100\">...</q>\n"
        "  <q score=\"0-100\">...</q>\n"
        "  ...\n"
        "</questions>\n\n"
        "Score meaning:\n"
        "- Score is a within-chunk estimate of retrieval utility.\n"
        "- Higher scores should go to questions that are:\n"
        "  grounded,\n"
        "  distinct,\n"
        "  standalone,\n"
        "  entity-rich when appropriate,\n"
        "  and likely to help hybrid retrieval.\n"
        "- Use the score to rank meaningfully within this chunk.\n\n"
        f"Text snippet:\n{snippet}\n"
    )


def main():
    parser = argparse.ArgumentParser(description="Improve question quality in semantic work files.")
    parser.add_argument("--config", default="", help="Path to runtime config JSON (default: postprocess_config.json).")
    parser.add_argument("--pattern", default="securitybooks/.semantic_work/*_semantic_work.json")
    parser.add_argument("--in-place", action="store_true", help="Modify files in place (default writes *_qv2.json).")
    parser.add_argument("--status-file", default="securitybooks/.semantic_work/.post_questions_status.json")
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
            prompt = build_prompt(text=text)

            raw = safe_chat_completion(
                client=client,
                controller=controller,
                model=model,
                prompt_text=prompt,
                max_tokens=256,
                temperature=0.2,
            )
            candidates = extract_scored_question_candidates(raw)
            best_q = candidates[0][1] if candidates else ""
            alt_qs = [q for _, q in candidates[1:3]] if len(candidates) > 1 else []

            use_new = bool(best_q)
            if use_new:
                block["question"] = best_q
                if alt_qs:
                    block["alt_questions"] = alt_qs
                else:
                    block.pop("alt_questions", None)
            if use_new:
                replaced += 1
            done.add(idx)
            print(
                f"[Q] idx={idx+1}/{len(blocks)} replaced={use_new} candidates={len(candidates)}"
            )

            file_state["done_indices"] = sorted(done)
            file_state["replaced"] = int(file_state.get("replaced", 0)) + (1 if use_new else 0)
            save_status(args.status_file, status)

        out_path = path if args.in_place else path.replace("_semantic_work.json", "_semantic_work_qv2.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)

        total_replaced += replaced
        print(f"[DONE] {path} replaced_questions={replaced} output={out_path}")

    status["finished_at"] = now_iso()
    status["total_questions_replaced"] = total_replaced
    save_status(args.status_file, status)
    print(f"[SUMMARY] total_questions_replaced={total_replaced}")


if __name__ == "__main__":
    main()
