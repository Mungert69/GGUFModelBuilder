#!/usr/bin/env python3
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
import sys
import os
from datetime import datetime, timezone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "model-converter")))
from make_files import (
    upload_large_file,
    split_file_standard,
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

def get_remote_commit_time(api, repo_id, path_in_repo):
    try:
        metadata = api.get_hf_file_metadata(
            repo_id=repo_id,
            path_in_repo=path_in_repo,
            token=api_token,
        )
        commit_time = metadata.last_commit_date
        if commit_time and commit_time.tzinfo is None:
            return commit_time.replace(tzinfo=timezone.utc)
        return commit_time
    except Exception:
        return None

def should_upload_file(api, repo_id, local_path, path_in_repo):
    try:
        if not api.file_exists(repo_id=repo_id, path_in_repo=path_in_repo, token=api_token):
            return True
    except Exception:
        return True

    remote_time = get_remote_commit_time(api, repo_id, path_in_repo)
    if not remote_time:
        return True

    local_time = datetime.fromtimestamp(os.path.getmtime(local_path), tz=timezone.utc)
    return local_time > remote_time

def upload_file_with_path(api, repo_id, file_path, path_in_repo, quant_name):
    file_size = os.path.getsize(file_path)
    if file_size <= 49.5 * 1024**3:
        api.upload_file(
            path_or_fileobj=file_path,
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            token=api_token,
        )
        return True

    if not quant_name:
        print(f"⚠ Skipping chunking for large file without quant name: {file_path}")
        api.upload_file(
            path_or_fileobj=file_path,
            path_in_repo=path_in_repo,
            repo_id=repo_id,
            token=api_token,
        )
        return True

    print("🔪 Splitting large file...")
    chunks = split_file_standard(file_path, quant_name)
    rel_dir = os.path.dirname(path_in_repo)
    for chunk in chunks:
        chunk_name = os.path.basename(chunk)
        chunk_path_in_repo = chunk_name if not rel_dir else f"{rel_dir}/{chunk_name}"
        api.upload_file(
            path_or_fileobj=chunk,
            path_in_repo=chunk_path_in_repo,
            repo_id=repo_id,
            token=api_token,
        )
        os.remove(chunk)
    return True

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
    parser.add_argument(
        "--keep-files",
        action="store_true",
        help="Do not delete local files after successful upload",
    )
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
    for root, _, filenames in os.walk(args.upload_dir):
        for filename in filenames:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, args.upload_dir).replace("\\", "/")

            if rel_path == "README.md":
                continue

            if not os.path.isfile(file_path):
                continue

            if not should_upload_file(api, repo_id, file_path, rel_path):
                print(f"⏭️  Skipping {rel_path} (remote is newer or same)")
                continue

            quant_name = get_quant_name(filename)
            print(f"\n⬆ Uploading {rel_path}...")

            try:
                if os.path.dirname(rel_path):
                    if upload_file_with_path(api, repo_id, file_path, rel_path, quant_name):
                        if not args.keep_files:
                            try:
                                os.remove(file_path)
                                print(f"Deleted {rel_path} after successful upload")
                            except Exception as e:
                                print(f"Warning: Could not delete {rel_path}: {e}")
                else:
                    if upload_large_file(file_path, repo_id, quant_name):
                        if not args.keep_files:
                            try:
                                os.remove(file_path)
                                print(f"Deleted {filename} after successful upload")
                            except Exception as e:
                                print(f"Warning: Could not delete {filename}: {e}")
            except Exception as e:
                print(f"Error during upload of {rel_path}: {e}")

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
