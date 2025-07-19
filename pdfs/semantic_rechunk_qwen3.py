import json
import sys
import re
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

# -------- Settings --------
MODEL_NAME = "Qwen/Qwen3-0.6B"  # or "Qwen/Qwen3-7B-Chat" (if available)
WINDOW_SIZE = 20
OUTPUT_FILE = "aggregated_chunks.json"

def load_chunks(json_file):
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Use 'output' as the text chunk field (from previous script)
    return [item["output"] for item in data]

def build_prompt(numbered_chunks):
    numbered_str = "\n".join([f"[{i+1}] {chunk.strip()}" for i, chunk in enumerate(numbered_chunks)])
    prompt = (
        "You are a document structuring assistant. Your job is to group and merge ADJACENT blocks of text into larger, logical, self-contained sections. "
        "For each output, specify exactly which input blocks (by number) you used. Output a JSON array with fields 'input_chunks' (list of numbers) and 'aggregated_chunk' (string). "
        "Do not overlap or skip any input blocks. Use only adjacent blocks for each output.\n\n"
        f"{numbered_str}"
    )
    return prompt

def parse_llm_json(text):
    # Extract the first JSON array in the output (works for most chat models)
    m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if m:
        json_str = m.group(0)
        return json.loads(json_str)
    # Fallback: Try loading the whole text
    return json.loads(text)

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} input_chunks.json [output_file.json]")
        sys.exit(1)

    input_json = sys.argv[1]
    output_json = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_FILE

    print(f"Loading model {MODEL_NAME} ... (this may take 1-2 minutes on first run)")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, device_map="auto", trust_remote_code=True)
    pipe = pipeline("text-generation", model=model, tokenizer=tokenizer, max_new_tokens=2048)

    print(f"Reading input chunks from {input_json} ...")
    all_chunks = load_chunks(input_json)
    index = 0
    aggregated = []

    while index < len(all_chunks):
        window_chunks = all_chunks[index:index+WINDOW_SIZE]
        if not window_chunks:
            break
        prompt = build_prompt(window_chunks)
        print(f"Processing chunks {index+1}-{index+len(window_chunks)} with Qwen3...")

        # Qwen3 chat format
        messages = [
            {"role": "system", "content": "You are a helpful document assistant."},
            {"role": "user", "content": prompt}
        ]
        input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        output = pipe(input_text, do_sample=False, temperature=0.3)[0]["generated_text"]

        # Only parse the part after the prompt
        llm_response = output[len(input_text):].strip()
        try:
            groups = parse_llm_json(llm_response)
        except Exception as e:
            print("Failed to parse LLM output! Output was:\n", llm_response)
            raise e

        # Map input indices to absolute indices
        for group in groups:
            chunk_indices = group.get("input_chunks", [])
            true_indices = [index + i - 1 for i in chunk_indices]
            aggregated.append({
                "input_indices": true_indices,
                "aggregated_chunk": group["aggregated_chunk"]
            })
        # Move pointer to the highest used chunk index in this window + 1
        max_used = max([max(g["input_chunks"]) for g in groups])
        index += max_used

    print(f"Writing {len(aggregated)} aggregated chunks to {output_json} ...")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2)
    print("Done.")

if __name__ == "__main__":
    main()

