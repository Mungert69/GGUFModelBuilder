import argparse
from huggingface_hub import hf_hub_download, list_repo_files
import os
import time
import shutil
import platform

# Setup argument parsing
parser = argparse.ArgumentParser(description="Automate Hugging Face downloads and system shutdown.")
parser.add_argument("--repo_id", required=True, help="Hugging Face repository ID")
parser.add_argument("--file_name", required=True, help="File name to download")
parser.add_argument("--iterations", type=int, required=True, help="Number of times to repeat the process")
parser.add_argument("--delay", type=float, required=True, help="Delay between iterations in seconds")

args = parser.parse_args()

# Assign arguments
repo_id = args.repo_id
file_name = args.file_name
n = args.iterations
delay = args.delay

# List all files in the repository
files = list_repo_files(repo_id=repo_id)
if file_name not in files:
    print(f"Error: The file '{file_name}' does not exist in the repository.")
    exit()

# Cache directory location
hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub")

# Download, delete, and repeat
for i in range(n):
    print(f"Iteration {i + 1}/{n} started for file '{file_name}'...")
    try:
        # Force fresh download
        file_path = hf_hub_download(repo_id=repo_id, filename=file_name, force_download=True)
        print(f"Downloaded {file_name} to {file_path}")

        # Delete the downloaded file
        os.remove(file_path)

        # Clear the Hugging Face cache
        shutil.rmtree(hf_cache_dir, ignore_errors=True)
        print(f"Cache cleared. Waiting for {delay} seconds before next iteration...")
        time.sleep(delay)

    except Exception as e:
        print(f"An error occurred during iteration {i + 1}: {e}")

# Shutdown the system
print("All iterations completed. Shutting down the system...")
if platform.system() == "Windows":
    os.system("shutdown /s /t 0")
else:
    os.system("shutdown -h now")

