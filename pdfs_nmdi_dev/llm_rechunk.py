import json
import sys
import os
import time
import random
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
import semantic_rechunk_qwen3 as sr

# -------- Settings --------
MAX_TOKENS = 12000  # Model context window
CHUNK_TOKEN_LIMIT = 3000  # Target max tokens per chunk (leave room for prompt/response)
WINDOW_SIZE = 20
TIME_DELAY = 10
MAX_RETRIES = 3
BASE_DELAY = 8
TIME_DELAY = 10
MIN_CHUNK_TOKENS = 500  # Minimum tokens per merged chunk

from semantic_rechunk_qwen3 import (
    safe_chat_completion,
    split_text_to_max_tokens,
    build_boundary_prompt,
    get_semantic_block_end,
    summarize_text,
    write_second_json_file,
    build_adaptive_window
)

from prechunk import smart_prechunk, merge_chunks

def rechunk_text_file(input_file, output_json):
    config_path = os.path.join(os.path.dirname(__file__), "semantic_rechunk_config.json")
    runtime_config = sr.load_runtime_config(config_path)
    sr.apply_runtime_overrides(runtime_config)
    tokenizer = sr.get_tokenizer()
    model_name = sr.MODEL_NAME
    api_base_url = sr.NOVITA_API_URL
    api_key_env = sr.API_KEY_ENV
    max_context = sr.MAX_CONTEXT

    # Read JSONL or JSON array of {"input": ..., "output": ...}
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Extract the "output" field from each item
    paras = [item["output"].strip() for item in data if item.get("output", "").strip()]
    # Use shared prechunking and merging logic

    chunks = []
    for idx, para in enumerate(paras):
        smart_chunks = smart_prechunk(para, tokenizer, CHUNK_TOKEN_LIMIT)
        print(f"[DEBUG] Output {idx+1}: {len(smart_chunks)} smart chunks found.")
        merged_chunks = merge_chunks(smart_chunks, tokenizer, MIN_CHUNK_TOKENS)
        for m_idx, chunk in enumerate(merged_chunks):
            preview = chunk[:80].replace('\n', ' ')
            ellipsis = "…" if len(chunk) > 80 else ""
            token_count = len(tokenizer.encode(chunk))
            print(f"  [DEBUG] Merged chunk {m_idx+1}: {preview}{ellipsis} [tokens: {token_count}]")
            # If chunk is still too big, split by tokens
            chunks.extend(split_text_to_max_tokens(chunk, CHUNK_TOKEN_LIMIT))
    print(f"[INFO] Initial rough chunks: {len(chunks)}")
    # Setup LLM client
    load_dotenv()
    api_key = os.getenv(api_key_env)
    if not api_key:
        print(f"[FATAL ERROR] Missing API key ({api_key_env}) in environment.")
        sys.exit(1)
    client = OpenAI(base_url=api_base_url, api_key=api_key)
    pointer = 0
    semantic_blocks = []
    adaptive_window_size = WINDOW_SIZE
    adaptive_mode = getattr(sr, "ADAPTIVE_WINDOW", True)
    adaptive_mode_logged = False

    while pointer < len(chunks):
        SAFETY_BUFFER = 100  # tokens
        reserved_output_tokens = MAX_TOKENS + SAFETY_BUFFER
        window_chunks, total_tokens, cur_window_size = build_adaptive_window(
            chunks, pointer, adaptive_window_size, tokenizer, build_boundary_prompt, max_context, reserved_output_tokens
        )

        # ---- Adaptive window size logic ----
        if adaptive_mode:
            fill_ratio = total_tokens / max_context
            if fill_ratio < 0.5 and adaptive_window_size < 50:
                adaptive_window_size += 2
                print(f"[ADAPT] Prompt fill ratio low ({fill_ratio:.2f}), increasing window size to {adaptive_window_size}")
            elif fill_ratio > 0.9 and adaptive_window_size > 2:
                adaptive_window_size = max(2, adaptive_window_size - 2)
                print(f"[ADAPT] Prompt fill ratio high ({fill_ratio:.2f}), decreasing window size to {adaptive_window_size}")
            else:
                print(f"[ADAPT] Prompt fill ratio ok ({fill_ratio:.2f}), keeping window size at {adaptive_window_size}")
        elif not adaptive_mode_logged:
            print(f"[ADAPT] Disabled. Using fixed window size {adaptive_window_size}")
            adaptive_mode_logged = True

        # ---- DEBUG PRINTS ----
        print("\n=== BLOCK DEBUG ===")
        print(f"Pointer before: {pointer}")
        print(f"Window size   : {cur_window_size}")
        print(f"Window chunks : {list(range(pointer + 1, pointer + cur_window_size + 1))}")
        print(f"Prompt tokens : {total_tokens}")
        for idx, chunk in enumerate(window_chunks):
            preview = chunk[:60].replace('\n', ' ')
            print(f"  [{pointer + idx + 1}] {preview}{'…' if len(chunk) > 60 else ''}")
        # ---- END DEBUG PRINTS ----

        if not window_chunks:
            print(f"[FATAL] Could not fit any chunks in context window at pointer {pointer}.")
            sys.exit(1)

        # Now, calculate the actual max tokens for output (in case prompt is close to the limit)
        available_output_tokens = max_context - total_tokens
        actual_max_tokens = min(MAX_TOKENS, available_output_tokens)
        if actual_max_tokens < 128:
            print(f"[FATAL] Not enough room for output tokens (only {actual_max_tokens} left).")
            sys.exit(1)

        end_idx, debug_msg = get_semantic_block_end(
            window_chunks, client, model_name, actual_max_tokens
        )
        if end_idx is None:
            print("\n" + "=" * 60 + "\nFATAL segmentation error\n" + "=" * 60)
            print(debug_msg)
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)
            sys.exit(1)
        if end_idx < 1 or end_idx > len(window_chunks):
            print(f"[ERROR] LLM returned invalid index: {end_idx}. Aborting.")
            break
        corrected_end = end_idx - 1 if end_idx > 1 else 1
        block_text = "\n\n".join(window_chunks[:corrected_end])

        print(f"[DEBUG] LLM response: {end_idx}")
        print(f"[DEBUG] Block: start={pointer + 1}, end={pointer + corrected_end}")
        print("[DEBUG] Chunks added to output:")
        for i in range(corrected_end):
            preview = window_chunks[i][:60].replace('\n', ' ')
            ellipsis = '…' if len(window_chunks[i]) > 60 else ''
            print(f"  [{pointer + i + 1}] {preview}{ellipsis}")

        # Generate question and summary using the shared function
        question, summary = summarize_text(block_text, client, model_name)
        semantic_blocks.append({
            "start": pointer + 1,
            "end": pointer + corrected_end,
            "text": block_text,
            "question": question,
            "summary": summary,
        })
        pointer += corrected_end
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Done. Wrote {len(semantic_blocks)} blocks to {output_json}")

    # Write the second JSON file for reusability
    write_second_json_file(input_file, output_json)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} input.txt output.json")
        sys.exit(1)
    rechunk_text_file(sys.argv[1], sys.argv[2])
