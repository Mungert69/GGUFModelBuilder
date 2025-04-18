#!/usr/bin/env python3
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
from make_files import (
    upload_large_file,
    QUANT_CONFIGS,
    api_token,
    base_dir
)
import os
import argparse
import shutil

def get_quant_name(filename):
    """EXACT same logic as the working version"""
    for config in QUANT_CONFIGS:
        if f"-{config[0]}.gguf" in filename:
            return config[0]
    if 'imatrix' in filename.lower():
        return "imatrix"
    return None

def main():
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
    try:
        api.create_repo(args.repo_id, exist_ok=True, token=api_token)
        print(f"Repository {args.repo_id} is ready.")
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
                repo_id=args.repo_id,
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
            if upload_large_file(file_path, args.repo_id, quant_name):
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
