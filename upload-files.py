#!/usr/bin/env python3
from make_files import (
    upload_large_file,
    QUANT_CONFIGS,
    base_dir,
    api_token
)
from huggingface_hub import login
from dotenv import load_dotenv
import os
import argparse
import shutil

# Load environment and authenticate
load_dotenv()
try:
    login(token=api_token)
    print("Authentication successful.")
except Exception as e:
    print(f"Authentication failed: {e}")
    exit()

def get_quant_name(filename):
    """Get exact quant name from filename using QUANT_CONFIGS"""
    for config in QUANT_CONFIGS:
        if f"-{config[0]}.gguf" in filename:
            return config[0]
    if 'imatrix' in filename.lower():
        return "imatrix"
    if "bf16.gguf" in filename.lower():
        return "bf16"
    return None

def main():
    parser = argparse.ArgumentParser(description="Upload GGUF files")
    parser.add_argument("model_name", help="Base model name (e.g. watt-tool-70b)")
    args = parser.parse_args()

    model_base = args.model_name
    repo_id = f"Mungert/{model_base}-GGUF"
    upload_dir = os.path.join(base_dir, model_base)
    hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub/")

    if not os.path.exists(upload_dir):
        print(f"Error: Directory not found - {upload_dir}")
        exit(1)

    # Upload all files
    for filename in os.listdir(upload_dir):
        filepath = os.path.join(upload_dir, filename)
        if not os.path.isfile(filepath):
            continue

        quant_name = get_quant_name(filename)
        print(f"\n⬆ Uploading {filename}...")
        upload_large_file(filepath, repo_id, quant_name)

    # Cleanup (identical to old version)
    if os.path.exists(upload_dir):
        try:
            print(f"\n🧹 Deleting {upload_dir}...")
            shutil.rmtree(upload_dir)
        except Exception as e:
            print(f"⚠ Cleanup failed: {e}")

    if os.path.exists(hf_cache_dir):
        try:
            print(f"🧹 Clearing Hugging Face cache...")
            shutil.rmtree(hf_cache_dir)
            os.makedirs(hf_cache_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠ Cache cleanup failed: {e}")

    print("\n🎉 Upload and cleanup completed!")

if __name__ == "__main__":
    main()
