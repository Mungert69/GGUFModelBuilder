#!/usr/bin/env python3
import subprocess
import re
import time
import csv
from pathlib import Path

# Configuration
BIN_DIR = Path("./llama.cpp")
INPUT_MODEL = Path("./Meta-Llama-3-8B-bf16.gguf")
TEST_TEXT = Path("./perplexity_test_data.txt")
IMATRIX_FILE = Path("./imatrix-files/Meta-Llama-3-8B.imatrix")
MIN_TOKENS = 4160
RESULTS_FILE = Path("./quantization_results.csv")
QUANTS = [
    "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ2_M",
    "IQ1_S", "IQ1_M",
    "Q2_K", "Q2_K_S",
    "IQ3_XXS", "IQ3_XS", "IQ3_S", "IQ3_M",
    "Q3_K", "Q3_K_S", "Q3_K_M", "Q3_K_L",
    "IQ4_NL", "IQ4_XS"
]

# Get thread count safely
try:
    THREADS = int(subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip())
except:
    THREADS = 4  # Fallback value

CTX_SIZE = 256
PPL_STRIDE = 32
CHUNKS = 1

def estimate_tokens(filepath):
    """Estimate tokens from word count"""
    with open(filepath) as f:
        return int(len(f.read().split()) * 0.75)

def prepare_test_data():
    """Download or generate test data"""
    sources = [
        "https://www.gutenberg.org/files/1661/1661-0.txt",
        "https://huggingface.co/datasets/roneneldan/TinyStories/resolve/main/TinyStoriesV2-GPT4-train.txt"
    ]
    
    for url in sources:
        try:
            subprocess.run(["wget", "-q", "--tries=2", "--timeout=30", url, "-O", str(TEST_TEXT)], check=True)
            if estimate_tokens(TEST_TEXT) >= MIN_TOKENS:
                print(f"Downloaded test data (~{estimate_tokens(TEST_TEXT):.0f} tokens)")
                return
        except:
            continue
    
    # Fallback generation
    with open(TEST_TEXT, "w") as f:
        f.write("[System Prompt] Test data\n")
        for i in range(1, 51):
            f.write(f"Sample {i}: The quick brown fox jumps over the lazy dog.\n")
    print(f"Generated test data (~{estimate_tokens(TEST_TEXT):.0f} tokens)")

def extract_perplexity(output):
    """Extract perplexity from output - WORKS WITH YOUR EXACT FORMAT"""
    # First try to find the specific pattern in your output
    lines = output.split('\n')
    for i, line in enumerate(lines):
        if "ETA" in line and i+1 < len(lines):
            next_line = lines[i+1].strip()
            if match := re.match(r'^\d+\s+(\d+\.\d+)$', next_line):
                return match.group(1)
    
    # Fallback patterns if the output format changes
    if match := re.search(r'Perplexity:\s*(\d+\.\d+)', output):
        return match.group(1)
    if match := re.search(r'\[\d+\](\d+\.\d+)', output):
        return match.group(1)
    
    return None

def run_command(cmd, log_file=None):
    """Run command with logging and timing"""
    start = time.time()
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, check=True)
        output = result.stdout
        duration = time.time() - start
        
        if log_file:
            with open(log_file, 'a') as f:
                f.write(f"=== Command: {' '.join(cmd)} ===\n")
                f.write(output)
                if result.stderr:
                    f.write("\n=== Errors ===\n")
                    f.write(result.stderr)
                f.write(f"\n=== Completed in {duration:.2f}s ===\n\n")
        
        return output, duration, True
    except subprocess.CalledProcessError as e:
        output = e.stdout
        if log_file:
            with open(log_file, 'a') as f:
                f.write(f"=== FAILED Command: {' '.join(cmd)} ===\n")
                f.write(output)
                if e.stderr:
                    f.write("\n=== Errors ===\n")
                    f.write(e.stderr)
                f.write(f"\n=== Failed after {time.time()-start:.2f}s ===\n\n")
        return output, time.time()-start, False

def main():
    """Main execution function"""
    # Initialize results
    with open(RESULTS_FILE, 'w') as f:
        f.write("Quantization,Perplexity,Time\n")

    # Prepare test data
    if not TEST_TEXT.exists() or estimate_tokens(TEST_TEXT) < MIN_TOKENS:
        print("Preparing test data...")
        prepare_test_data()

    # Test each quantization type
    for ftype in QUANTS:
        output_model = Path(f"./Meta-Llama-3-8B-{ftype}.gguf")
        log_file = Path(f"./quantize_{ftype}.log")
        
        print(f"\n=== Testing {ftype} ===")
        print(f"[{time.strftime('%H:%M:%S')}] Output: {output_model}")

        # Quantization
        if not output_model.exists():
            quant_cmd = [
                str(BIN_DIR/"llama-quantize"),
                "--imatrix", str(IMATRIX_FILE),
                "--token-embedding-type", "q5_k",
                "--output-tensor-type", "q5_k",
                str(INPUT_MODEL),
                str(output_model),
                ftype
            ]
            print(f"Quantizing: {' '.join(quant_cmd)}")
            _, quant_time, success = run_command(quant_cmd, log_file)
            if not success:
                print("ERROR: Quantization failed")
                continue
        else:
            print("Existing model found, skipping quantization")
            quant_time = 0

        # Perplexity Test
        if output_model.exists():
            print(f"\n[{time.strftime('%H:%M:%S')}] Running perplexity test...")
            ppl_cmd = [
                str(BIN_DIR/"llama-perplexity"),
                "-m", str(output_model),
                "-f", str(TEST_TEXT),
                "--ctx-size", str(CTX_SIZE),
                "--ppl-stride", str(PPL_STRIDE),
                "--chunks", str(CHUNKS),
                "--threads", str(THREADS)
            ]
            print(f"Running: {' '.join(ppl_cmd)}")
            output, ppl_time, success = run_command(ppl_cmd, log_file)
            
            final_ppl = extract_perplexity(output)
            if final_ppl:
                print(f"[✓] Perplexity: {final_ppl} (Time: {ppl_time:.2f}s)")
                with open(RESULTS_FILE, 'a') as f:
                    f.write(f"{ftype},{final_ppl},{ppl_time:.2f}\n")
            else:
                print("[X] Failed to extract perplexity - dumping output for debugging:")
                print("="*60)
                print(output[-500:])  # Show last 500 chars of output
                print("="*60)
                with open(RESULTS_FILE, 'a') as f:
                    f.write(f"{ftype},ERROR,\n")

if __name__ == "__main__":
    main()
    print(f"\nResults saved to {RESULTS_FILE}")
