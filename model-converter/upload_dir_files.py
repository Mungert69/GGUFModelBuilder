#!/usr/bin/env python3
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "model-converter")))
from make_files import (
    upload_large_file,
    QUANT_CONFIGS,
    api_token,
    base_dir
)
import argparse
import shutil

def get_quant_name(filename):
    """EXACT same logic as the working version"""
    for config in QUANT_CONFIGS:
        if f"-{config[0]}.gguf" in filename:
            return config[0]
    if 'imatrix' in filename.lower():
        return "imatrix"
    if "bf16.gguf" in filename.lower():
        return "bf16"
    return None

def main():
    # Load username from file
    with open(os.path.join(os.path.dirname(__file__), "username"), "r") as f:
        HF_USERNAME = f.read().strip()
    # Authentication (same as before)
    load_dotenv()
    try:
        login(token=api_token)
        print("Authentication successful.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        exit()

    # Parse arguments
    parser = argparse.ArgumentParser(description="Upload files to Hugging Face")
    parser.add_argument("repo_id", help="HF repository ID (e.g., Mungert/gemma-3-12b-it-GGUF)")
    parser.add_argument("upload_dir", help="Directory containing files to upload")
    args = parser.parse_args()

    # Repo creation
    api = HfApi()
    # Replace Mungert with HF_USERNAME in repo_id if present
    repo_id = args.repo_id.replace("Mungert", HF_USERNAME)
    try:
        api.create_repo(repo_id, exist_ok=True, token=api_token)
        print(f"Repository {repo_id} is ready.")
    except Exception as e:
        print(f"Error creating repository: {e}")
        exit()

    # README handling (same)
    readme_path = os.path.join(args.upload_dir, "README.md")
    if os.path.isfile(readme_path):
        try:
            print("Uploading README.md...")
            api.upload_file(
                path_or_fileobj=readme_path,
                path_in_repo="README.md",
                repo_id=repo_id,
                token=api_token,
            )
            print("Uploaded README.md successfully.")
        except Exception as e:
            print(f"Error uploading README.md: {e}")

    # File upload with EXACT same quant handling
    for filename in os.listdir(args.upload_dir):
        file_path = os.path.join(args.upload_dir, filename)
        
        if not os.path.isfile(file_path) or filename == "README.md":
            continue

        # This is the crucial matching part
        quant_name = get_quant_name(filename)
        print(f"\n⬆ Uploading {filename}...")
        
        try:
            if upload_large_file(file_path, repo_id, quant_name):
                try:
                    os.remove(file_path)
                    print(f"Deleted {filename} after successful upload")
                except Exception as e:
                    print(f"Warning: Could not delete {filename}: {e}")
        except Exception as e:
            print(f"Error during upload of {filename}: {e}")

    # Cache cleanup (same as your working version)
    hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub/")
    if os.path.exists(hf_cache_dir):
        try:
            print(f"🧹 Clearing Hugging Face cache...")
            shutil.rmtree(hf_cache_dir)
            os.makedirs(hf_cache_dir, exist_ok=True)
        except Exception as e:
            print(f"⚠ Cache cleanup failed: {e}")

    print("\n🎉 Upload process completed!")

if __name__ == "__main__":
    main()
