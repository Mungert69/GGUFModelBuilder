#!/usr/bin/env python3
import subprocess
import re
import time
import csv
from pathlib import Path
import argparse

# Configuration
BIN_DIR = Path("./llama.cpp")
TEST_TEXT = Path("./perplexity_test_data.txt")
MIN_TOKENS = 4160
RESULTS_FILE = Path("./model_comparison.csv")
CTX_SIZE = 256
PPL_STRIDE = 32
CHUNKS = 1
THREADS=4

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
    """Extract perplexity from output"""
    lines = output.split('\n')
    for i, line in enumerate(lines):
        if "ETA" in line and i+1 < len(lines):
            next_line = lines[i+1].strip()
            if match := re.match(r'^\d+\s+(\d+\.\d+)$', next_line):
                return match.group(1)
    
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

def test_model(model_path, log_file=None):
    """Run perplexity test on a single model"""
    print(f"\nTesting model: {model_path.name}")
    
    ppl_cmd = [
        str(BIN_DIR/"llama-perplexity"),
        "-m", str(model_path),
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
        return float(final_ppl), ppl_time
    else:
        print("[X] Failed to extract perplexity - dumping output for debugging:")
        print("="*60)
        print(output[-500:])
        print("="*60)
        return None, None

def main():
    """Main execution function"""
    parser = argparse.ArgumentParser(description='Compare perplexity of two GGUF models')
    parser.add_argument('model1', type=str, help='Path to first GGUF model file')
    parser.add_argument('model2', type=str, help='Path to second GGUF model file')
    args = parser.parse_args()

    # Get thread count safely
    try:
        THREADS = int(subprocess.run(["nproc"], capture_output=True, text=True).stdout.strip())
    except:
        THREADS = 4  # Fallback value

    # Prepare test data
    if not TEST_TEXT.exists() or estimate_tokens(TEST_TEXT) < MIN_TOKENS:
        print("Preparing test data...")
        prepare_test_data()

    # Initialize results
    with open(RESULTS_FILE, 'w') as f:
        f.write("Model,Perplexity,Time\n")

    # Test both models
    results = []
    for model_path in [Path(args.model1), Path(args.model2)]:
        if not model_path.exists():
            print(f"Error: Model file not found: {model_path}")
            return
        
        log_file = Path(f"./perplexity_{model_path.stem}.log")
        ppl, duration = test_model(model_path, log_file)
        
        if ppl is not None:
            results.append((model_path.name, ppl, duration))
            with open(RESULTS_FILE, 'a') as f:
                f.write(f"{model_path.name},{ppl},{duration:.2f}\n")

    # Print comparison
    if len(results) == 2:
        print("\n=== Comparison Results ===")
        print(f"Model 1: {results[0][0]} - Perplexity: {results[0][1]:.2f} (Time: {results[0][2]:.2f}s)")
        print(f"Model 2: {results[1][0]} - Perplexity: {results[1][1]:.2f} (Time: {results[1][2]:.2f}s)")
        
        diff = results[0][1] - results[1][1]
        winner = results[0][0] if diff < 0 else results[1][0]
        print(f"\nWinner: {winner} (Difference: {abs(diff):.2f})")

if __name__ == "__main__":
    main()
    print(f"\nResults saved to {RESULTS_FILE}")
