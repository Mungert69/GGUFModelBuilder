import json
import sys
import re
import os
import time
import random
import pathlib
import shutil
import glob
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from transformers import AutoTokenizer

# -------- Settings --------
MODEL_NAME = "qwen/qwen3-4b-fp8"
MAX_TOKENS = 6000  # For remote model, as per API
WINDOW_SIZE = 20
TIME_DELAY = 10
OUTPUT_FILE = "semantic_blocks.json"
NOVITA_API_URL = "https://api.novita.ai/v3/openai"

# LLM context window size (tokens)
MAX_CONTEXT = 40960  # Set this to your model's context window

MAX_RETRIES = 3           # how many times to try
BASE_DELAY  = 8           # s – exponential back‑off base

tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-4B")



def split_text_to_max_tokens(text, max_tokens):
    tokens = tokenizer.encode(text)
    if len(tokens) <= max_tokens:
        return [text]
    # Split into multiple pieces
    splits = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i+max_tokens]
        chunk_text = tokenizer.decode(chunk_tokens)
        splits.append(chunk_text)
    return splits

def build_adaptive_window(
    chunks, pointer, adaptive_window_size, tokenizer, build_boundary_prompt, max_context, reserved_output_tokens
):
    """
    Dynamically build a window of chunks that fits within the LLM context window.
    Returns (window_chunks, total_tokens, cur_window_size)
    """
    window_chunks = []
    total_tokens = 0
    for i in range(adaptive_window_size):
        if pointer + i >= len(chunks):
            break
        candidate_chunk = chunks[pointer + i]
        temp_chunks = window_chunks + [candidate_chunk]
        prompt = build_boundary_prompt(temp_chunks)
        prompt_tokens = len(tokenizer.encode(prompt))
        if prompt_tokens > max_context - reserved_output_tokens:
            break
        window_chunks.append(candidate_chunk)
        total_tokens = prompt_tokens
    cur_window_size = len(window_chunks)
    return window_chunks, total_tokens, cur_window_size

def load_chunks(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"[INFO] Loaded {len(data)} chunks from {json_file}")
    return [item["output"] for item in data]
def resume_previous(output_json: str):
    """
    If an output file already exists, read any previously written
    semantic blocks and return (blocks, last_processed_chunk_index).
    Returns ([], 0) if there is nothing to resume.
    """
    if not os.path.exists(output_json):
        return [], 0

    try:
        with open(output_json, "r", encoding="utf-8") as f:
            blocks = json.load(f)
        if isinstance(blocks, list) and blocks:
            last_end = blocks[-1].get("end", 0)
            if isinstance(last_end, int) and last_end >= 0:
                return blocks, last_end          # 1‑based index from the JSON
    except Exception as exc:
        print(f"[WARN] Could not read {output_json}: {exc!r}")

    return [], 0

def build_boundary_prompt(numbered_chunks):
    """
    Return a prompt that asks the LLM for the **index of the first chunk
    that starts the *next* major section** inside the sliding window.
    """
    chunks_json = json.dumps(
        [{"index": i + 1, "text": chunk.strip()}
         for i, chunk in enumerate(numbered_chunks)],
        ensure_ascii=False,
        indent=2
    )
    n_chunks = len(numbered_chunks)

    prompt = (
        # ---------- task ----------
        "Below is a JSON array of document chunks, each with an \"index\" and \"text\".\n\n"
        "★ **Task:** Return the **index of the FIRST CHUNK that begins the NEXT major section / heading / chapter / topic.**\n"
        "That is, imagine the window as `[current‑section … | next‑section …]`; "
        "your answer is the index where the divider `|` sits.\n"
        "⚠️ Do **NOT** return the index of the last chunk in the current section.\n"
        "⚠️ Do **NOT** return the number of chunks.\n\n"
        "Prefer to group *more* chunks rather than splitting on minor transitions (page numbers, pictures, charts etc.).\n"
        "• A heading‑like chunk (ALL‑CAPS line, \"Chapter …\", numbered title) **does not by itself mark a boundary**. "
        "Treat the heading and its immediate introductory paragraph(s) as one unit. "
        "Only mark a boundary when the following chunk clearly shifts topic.\n\n"

        "[BEGIN_EXAMPLES]\n"

        "Example 1:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Copyright\"},\n"
        "  {\"index\": 2, \"text\": \"Table of Contents\"},\n"
        "  {\"index\": 3, \"text\": \"Preface\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 1: Getting Started\"},\n"
        "  {\"index\": 5, \"text\": \"Chapter 1 content…\"}\n"
        "]\n"
        "✔ Correct response: **4**  (chunk 4 is the first of Chapter 1)\n\n"

        "Example 2:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Chapter 1: The Basics\"},\n"
        "  {\"index\": 2, \"text\": \"More on chapter 1\"},\n"
        "  {\"index\": 3, \"text\": \"Still more on chapter 1\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 2: Advanced Topics\"},\n"
        "  {\"index\": 5, \"text\": \"Content on chapter 2\"}\n"
        "]\n"
        "✔ Correct response: **4**\n\n"

        "Example 3:\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Section 2.4: Analysis of Results\"},\n"
        "  {\"index\": 2, \"text\": \"Detailed explanation of the experimental setup …\"},\n"
        "  {\"index\": 3, \"text\": \"Figure 2‑7: Distribution of sample values\"},\n"
        "  {\"index\": 4, \"text\": \"Continuation of analysis and discussion …\"},\n"
        "  {\"index\": 5, \"text\": \"Section 2.5: Limitations\"}\n"
        "]\n"
        "✔ Correct response: **5**  (chunk 5 is the first chunk of the next real section; the figure caption at chunk 3 does **not** define a boundary)\n\n"
        "✖ Wrong response : **3** (that is figure not a boundary)\n\n"

        "Counter‑example (#4):\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"Chapter 1 intro\"},\n"
        "  {\"index\": 2, \"text\": \"Chapter 1 body\"},\n"
        "  {\"index\": 3, \"text\": \"Chapter 1 summary\"},\n"
        "  {\"index\": 4, \"text\": \"Chapter 2: Advanced\"},\n"
        "  {\"index\": 5, \"text\": \"Chapter 2 body\"}\n"
        "]\n"
        "✔ Correct response: **4**\n"
        "✖ Wrong response : **3** (that is the last chunk of Chapter 1, NOT the first of Chapter 2)\n\n"

        "Counter‑example (#5 – heading travels with intro):\n"
        "[\n"
        "  {\"index\": 1, \"text\": \"CHAPTER 2: INTRODUCTION\"},\n"
        "  {\"index\": 2, \"text\": \"This chapter covers the basics of …\"},\n"
        "  {\"index\": 3, \"text\": \"More details on the basics …\"},\n"
        "  {\"index\": 4, \"text\": \"CHAPTER 3: ADVANCED TOPICS\"}\n"
        "]\n"
        "✔ Correct response: **4**\n"
        "✖ Wrong response : **2** or **3** (heading + intro are one unit)\n"

        "[END_EXAMPLES]\n\n"

        # ---------- actual data ----------
        "Now decide the boundary for the real data below. "
        f"Respond with a single integer from **1** to **{n_chunks}** — "
        "no explanation, no extra text.\n\n"
        "[BEGIN_CHUNKS]\n"
        f"{chunks_json}\n"
        "[END_CHUNKS]\n"
        "Reply with the index only:"
    )
    return prompt

def get_semantic_block_end(window_chunks, client, model, max_tokens):
    prompt = build_boundary_prompt(window_chunks)

    try:
        chat_completion_res = safe_chat_completion(
            client=client,
            prompt_text=prompt,
            model=model,
            stream=False,
            max_tokens=max_tokens,
            temperature=0.3,
            top_p=1,
            presence_penalty=0,
            frequency_penalty=0,
            response_format={"type": "text"},
            extra_body={"top_k": 50,
                        "repetition_penalty": 1,
                        "min_p": 0}
        )
    except Exception as e:
        return None, f"[API‑ERROR] {e}"

    time.sleep(TIME_DELAY)

    if not chat_completion_res.choices:
        return None, "[API‑ERROR] 0 choices returned"

    llm_response = (chat_completion_res.choices[0].message.content or "").strip()

    numbers = re.findall(r"\b(\d{1,3})\b", llm_response)
    if not numbers:
        return None, f"[PARSE‑ERROR] No integer in response: {llm_response!r}"

    return int(numbers[-1]), llm_response

def print_window(pointer, window_chunks):
    print(f"\n[WINDOW] Chunks {pointer+1} to {pointer+len(window_chunks)}:")
    for i, chunk in enumerate(window_chunks):
        chunk_preview = chunk[:100].replace('\n', ' ')
        ellipsis = '...' if len(chunk) > 100 else ''
        print(f"  [{pointer + i + 1}] {chunk_preview}{ellipsis}")

def summarize_text(text, client, model):
    """
    Generate a question and summary for a given text block using the LLM.
    Returns (question, summary).
    """
    print(f"[DEBUG] Generating question for block text (length={len(text)}):")
    print(f"[DEBUG] Text preview: {text[:120].replace(chr(10), ' ')}{'...' if len(text) > 120 else ''}")
    question_prompt = (
        "Read the following text and write a single, clear question that could be answered by understanding this section. "
        "The question should help a reader focus on the key topic or concept discussed. "
        "Do not include any <think> tags or internal reasoning. /no_think\n\n"
        f"{text}\n"
    )
    try:
        question_resp = safe_chat_completion(
            client=client,
            prompt_text=question_prompt,
            model=model,
            stream=False,
            max_tokens=256,
            temperature=0.3,
            top_p=1,
            presence_penalty=0,
            frequency_penalty=0,
            response_format={"type": "text"},
            extra_body={"top_k": 50, "repetition_penalty": 1, "min_p": 0}
        )
        question = (question_resp.choices[0].message.content or "").strip()
        question = re.sub(r"<think>.*?</think>\s*", "", question, flags=re.DOTALL | re.IGNORECASE)
        print(f"[DEBUG] Question result: {question[:120]}{'...' if len(question) > 120 else ''}")
    except Exception as e:
        print(f"[WARN] Could not generate question: {e!r}")
        question = ""
    time.sleep(TIME_DELAY)

    print(f"[DEBUG] Generating summary for block text (length={len(text)}):")
    summary_prompt = (
        "Summarize the following text in 2-3 sentences, focusing on the main ideas. "
        "Keep it brief and concise. Do not include any <think> tags or internal reasoning. /no_think\n\n"
        f"{text}\n"
    )
    try:
        summary_resp = safe_chat_completion(
            client=client,
            prompt_text=summary_prompt,
            model=model,
            stream=False,
            max_tokens=256,
            temperature=0.3,
            top_p=1,
            presence_penalty=0,
            frequency_penalty=0,
            response_format={"type": "text"},
            extra_body={"top_k": 50, "repetition_penalty": 1, "min_p": 0}
        )
        summary = (summary_resp.choices[0].message.content or "").strip()
        summary = re.sub(r"<think>.*?</think>\s*", "", summary, flags=re.DOTALL | re.IGNORECASE)
        print(f"[DEBUG] Summary result: {summary[:120]}{'...' if len(summary) > 120 else ''}")
    except Exception as e:
        print(f"[WARN] Could not generate summary: {e!r}")
        summary = ""
    time.sleep(TIME_DELAY)
    return question, summary

def write_second_json_file(input_json, output_json):
    """
    Reads the semantic_blocks output file and writes a new JSON file
    with {"input": question, "summary": summary, "output": text} for each block.
    """
    new_dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
    new_base, new_ext = os.path.splitext(output_json)
    new_base = new_base.replace(' ', '_')
    new_filename = f"{new_base}_out_{new_dt_str}{new_ext}"

    with open(output_json, "r", encoding="utf-8") as f:
        blocks = json.load(f)

    new_array = [
        {
            "input": block.get("question", ""),
            "summary": block.get("summary", ""),
            "output": block.get("text", "")
        }
        for block in blocks
    ]

    with open(new_filename, "w", encoding="utf-8") as f:
        json.dump(new_array, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Created new file: {new_filename}")

def safe_chat_completion(client, prompt_text: str, **kwargs):
    """
    Wrapper that retries on empty‑choice responses / network hiccups.
    If all retries fail it writes the prompt + raw response to disk.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user",   "content": prompt_text}
                ],
                **kwargs
            )

            # ---------- happy path ----------
            if resp.choices:
                return resp

            # ---------- empty‑choices ----------
            print(f"[WARN] Empty 'choices' (attempt {attempt}/{MAX_RETRIES})")

        except Exception as e:
            print(f"[WARN] API exception {e!r} (attempt {attempt}/{MAX_RETRIES})")

        # back‑off before next try
        sleep_time = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 2)
        time.sleep(sleep_time)

    # ============== all retries failed  ==============
    dump_dir = pathlib.Path("llm_debug")
    dump_dir.mkdir(exist_ok=True)

    with (dump_dir / "failed_prompt.txt").open("w", encoding="utf-8") as f:
        f.write(prompt_text)

    # resp might be undefined if all attempts threw exceptions
    raw = resp.to_dict() if "resp" in locals() else {"error": "no response object"}
    with (dump_dir / "failed_response.json").open("w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2)

    raise RuntimeError("LLM API kept returning 0 choices (debug written to llm_debug/)")

def main():
    # -------- CLI parsing -------------------------------------------------
    import glob
    args = sys.argv[1:]
    resume = False
    mode = "single"
    if "--resume" in args:
        resume = True
        args.remove("--resume")
    if "--all" in args:
        mode = "all"
        args.remove("--all")
    if "--single" in args:
        mode = "single"
        args.remove("--single")

    if mode == "single" and len(args) < 1:
        print(
            f"Usage: {sys.argv[0]} input_chunks.json [output_file.json] [--resume] [--single|--all]\n"
            "  --resume   Continue from an existing semantic_blocks.json if present;\n"
            "             without it, any existing output file is backed up (.bak) and overwritten.\n"
            "  --single   (default) Process a single file (input_chunks.json)\n"
            "  --all      Process all .json files in the current directory that do not have a date suffix"
        )
        sys.exit(1)

    def process_one_file(input_json, output_json, resume):
        # -------- API client --------------------------------------------------
        load_dotenv()
        api_key = os.getenv("LlmHFKey")
        if not api_key:
            print("[FATAL ERROR] Missing API key (LlmHFKey) in .env file")
            sys.exit(1)
        client = OpenAI(base_url=NOVITA_API_URL, api_key=api_key)

        # -------- Load chunks --------------------------------------------------
        print(f"[INFO] Reading input chunks from {input_json} …")
        all_chunks = load_chunks(input_json)

        # --------- Check for oversized chunks and fallback to llm_rechunk if needed ---------
        oversized = False
        for idx, chunk in enumerate(all_chunks):
            token_count = len(tokenizer.encode(chunk))
            # MAX_CONTEXT is the LLM's hard limit, MAX_TOKENS is only for output
            if token_count > (MAX_CONTEXT - MAX_TOKENS):
                print(f"[FATAL] Chunk {idx+1} is too large for LLM context window ({token_count} tokens > {MAX_CONTEXT - MAX_TOKENS}). Falling back to llm_rechunk.py.")
                oversized = True
                break

        if oversized:
            import subprocess
            # Compose output file name
            dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
            print(f"[INFO] Calling llm_rechunk.py on {input_json} ...")
            subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), "llm_rechunk.py"), input_json, output_json],
                check=True
            )
            print(f"[INFO] llm_rechunk.py completed. Output: {output_json}")
            return

        # -------- Resume or start fresh ---------------------------------------
        if resume:
            semantic_blocks, pointer = resume_previous(output_json)
            if semantic_blocks:
                print(f"[INFO] Resuming from chunk {pointer} (next is {pointer + 1})")
            else:
                print("[INFO] No previous progress found – starting fresh.")
                semantic_blocks, pointer = [], 0
        else:
            if os.path.exists(output_json):
                shutil.copy2(output_json, output_json + ".bak")
                print(f"[INFO] Existing output file backed up to {output_json}.bak")
            semantic_blocks, pointer = [], 0
            # create/overwrite with empty list so downstream writes always succeed
            with open(output_json, "w", encoding="utf-8") as f:
                f.write("[]")

        # -------- Main loop ---------------------------------------------------
        SAFETY_BUFFER = 100  # tokens
        reserved_output_tokens = MAX_TOKENS + SAFETY_BUFFER
        adaptive_window_size = WINDOW_SIZE

        while pointer < len(all_chunks):
            # Dynamically build a window that fits in the context window
            window_chunks, total_tokens, cur_window_size = build_adaptive_window(
                all_chunks, pointer, adaptive_window_size, tokenizer, build_boundary_prompt, MAX_CONTEXT, reserved_output_tokens
            )

            # ---- Adaptive window size logic ----
            fill_ratio = total_tokens / MAX_CONTEXT if MAX_CONTEXT else 0
            if fill_ratio < 0.5 and adaptive_window_size < 50:
                adaptive_window_size += 2
                print(f"[ADAPT] Prompt fill ratio low ({fill_ratio:.2f}), increasing window size to {adaptive_window_size}")
            elif fill_ratio > 0.9 and adaptive_window_size > 2:
                adaptive_window_size = max(2, adaptive_window_size - 2)
                print(f"[ADAPT] Prompt fill ratio high ({fill_ratio:.2f}), decreasing window size to {adaptive_window_size}")
            else:
                print(f"[ADAPT] Prompt fill ratio ok ({fill_ratio:.2f}), keeping window size at {adaptive_window_size}")

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
                print(f"[FATAL] Could not fit any chunks in context window at pointer {pointer}. Skipping file.")
                return

            # Now, calculate the actual max tokens for output (in case prompt is close to the limit)
            available_output_tokens = MAX_CONTEXT - total_tokens
            # MAX_TOKENS is only for output, never for prompt
            actual_max_tokens = min(MAX_TOKENS, available_output_tokens)
            if actual_max_tokens < 128:
                print(f"[FATAL] Not enough room for output tokens (only {actual_max_tokens} left). Skipping file.")
                return

            end_idx, debug_msg = get_semantic_block_end(
                window_chunks, client, MODEL_NAME, actual_max_tokens
            )

            if end_idx is None:
                print("\n" + "=" * 60 + "\nFATAL segmentation error\n" + "=" * 60)
                print(debug_msg)
                with open(output_json, "w", encoding="utf-8") as f:
                    json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)
                print(f"[ERROR] Skipping file {input_json} due to fatal segmentation error.")
                return

            if end_idx < 1 or end_idx > len(window_chunks):
                print(f"[ERROR] LLM returned invalid index: {end_idx}. Aborting.")
                break

            corrected_end = end_idx - 1 if end_idx > 1 else 1
            block_text    = "\n".join(window_chunks[:corrected_end])

            print(f"[DEBUG] LLM response: {end_idx}")
            print(f"[DEBUG] Block: start={pointer + 1}, end={pointer + corrected_end}")
            print("[DEBUG] Chunks added to output:")
            for i in range(corrected_end):
                preview = window_chunks[i][:60].replace('\n', ' ')
                ellipsis = '…' if len(window_chunks[i]) > 60 else ''
                print(f"  [{pointer + i + 1}] {preview}{ellipsis}")

            question, summary = summarize_text(block_text, client, MODEL_NAME)
            semantic_blocks.append(
                {"start": pointer + 1, "end": pointer + corrected_end, "text": block_text, "question": question, "summary": summary}
            )

            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(semantic_blocks, f, ensure_ascii=False, indent=2)

            pointer += corrected_end  # advance to next unprocessed chunk

        print("[INFO] Done.")

        # --------- Write a second JSON file from the first (for reusability) ---------
        write_second_json_file(input_json, output_json)
        print(f"[INFO] Created new file: {output_json}")


    if "--all" in sys.argv:
        # Find all .json files in the current directory that do NOT have a date suffix
        all_jsons = glob.glob("*.json")
        date_pat = re.compile(r"_\d{14}(\.json)?$")
        to_process = [f for f in all_jsons if not date_pat.search(f)]
        # Only process files that do NOT have a corresponding _out_ file (completed job)
        filtered_to_process = []
        for f in to_process:
            input_base, _ = os.path.splitext(os.path.basename(f))
            # Look for any file with _out_ and the input_base in the name
            out_pattern = f"{input_base}_out_*.json"
            out_files = glob.glob(out_pattern)
            if out_files:
                # Check if the _out_ file is actually complete
                out_file = out_files[0]
                try:
                    with open(f, "r", encoding="utf-8") as fin:
                        input_data = json.load(fin)
                    with open(out_file, "r", encoding="utf-8") as fout:
                        out_data = json.load(fout)
                    if len(out_data) == len(input_data):
                        print(f"[INFO] Skipping {f} (already has complete _out_ file: {out_file})")
                        continue
                    else:
                        print(f"[WARN] _out_ file {out_file} is incomplete ({len(out_data)}/{len(input_data)} records). Will retry.")
                        # Empty the _out_ file so we can retry
                        with open(out_file, "w", encoding="utf-8") as fout:
                            json.dump([], fout)
                except Exception as e:
                    print(f"[WARN] Could not check completeness of {out_file}: {e!r}. Will retry.")
                    # Empty the _out_ file so we can retry
                    try:
                        with open(out_file, "w", encoding="utf-8") as fout:
                            json.dump([], fout)
                    except Exception as e2:
                        print(f"[ERROR] Could not empty {out_file}: {e2!r}")
            filtered_to_process.append(f)
        if not filtered_to_process:
            print("[INFO] No .json files found to process (all jobs completed).")
            sys.exit(0)
        for input_json in filtered_to_process:
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
            print(f"[INFO] Processing {input_json} ...")
            try:
                process_one_file(input_json, output_json, "--resume" in sys.argv)
            except Exception as e:
                print(f"[ERROR] Failed to process {input_json}: {e!r}")
                import traceback
                traceback.print_exc()
                continue
        print("[INFO] Batch processing complete.")
        sys.exit(0)
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        if len(args) < 1:
            print(
                f"Usage: {sys.argv[0]} input_chunks.json [output_file.json] [--resume] [--single|--all]\n"
                "  --resume   Continue from an existing semantic_blocks.json if present;\n"
                "             without it, any existing output file is backed up (.bak) and overwritten.\n"
                "  --single   (default) Process a single file (input_chunks.json)\n"
                "  --all      Process all .json files in the current directory that do not have a date suffix"
            )
            sys.exit(1)
        input_json = args[0]
        dt_str = datetime.now().strftime("%Y%m%d%H%M%S")
        if len(args) > 1:
            base_output = args[1]
            base, ext = os.path.splitext(base_output)
            output_json = f"{base.replace(' ', '_')}_{dt_str}{ext}"
        else:
            input_base, _ = os.path.splitext(os.path.basename(input_json))
            output_json = f"{input_base.replace(' ', '_')}_{dt_str}.json"
        process_one_file(input_json, output_json, "--resume" in sys.argv)

if __name__ == "__main__":
    main()
