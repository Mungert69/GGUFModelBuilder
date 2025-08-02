#!/usr/bin/env python3
"""
upload-files.py

This script uploads all GGUF model files from a specified model directory to the Hugging Face Hub,
using the correct quantization folder structure. After uploading, it cleans up the local model
directory and the Hugging Face cache.

Main Features:
- Authenticates with Hugging Face using credentials from the environment.
- Determines quantization type for each file using loaded quantization configs.
- Uploads each file to the appropriate folder in the Hugging Face repo.
- Cleans up the local model directory and Hugging Face cache after upload.

Functions:
    - get_quant_name(filename): Returns the quantization name for a given filename.
    - main(): Parses arguments, uploads files, and performs cleanup.

Usage:
    python upload-files.py <model_name>

Arguments:
    model_name: Base model name (e.g. watt-tool-70b).

Exits with code 0 on success, 1 on failure.
"""

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
    """Returns the quantization name for a given filename.

    This function inspects the filename and determines the quantization type based on known patterns.

    Args:
        filename: The name of the file to check.

    Returns:
        str or None: The quantization name if found, otherwise None.
    """

    for config in QUANT_CONFIGS:
        if f"-{config[0]}.gguf" in filename:
            return config[0]
    if 'imatrix' in filename.lower():
        return "imatrix"
    if "bf16.gguf" in filename.lower():
        return "bf16"
    return None

def main():
    """Uploads all GGUF model files from a specified directory to the Hugging Face Hub and performs cleanup.

    This function parses command-line arguments, uploads each GGUF file to the appropriate quantization folder, and cleans up local directories and cache.

    Returns:
        None

    Raises:
        SystemExit: If the specified model directory does not exist.
    """
    parser = argparse.ArgumentParser(description="Upload GGUF files")
    parser.add_argument("model_name", help="Base model name (e.g. watt-tool-70b)")
    args = parser.parse_args()

    # Load username from file
    with open(os.path.join(os.path.dirname(__file__), "username"), "r") as f:
        HF_USERNAME = f.read().strip()
    model_base = args.model_name
    repo_id = f"{HF_USERNAME}/{model_base}-GGUF"
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
