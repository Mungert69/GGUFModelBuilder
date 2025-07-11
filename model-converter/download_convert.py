"""
download_convert.py

This script downloads a model from the Hugging Face Hub, converts it to BF16 GGUF format using llama.cpp,
adds metadata, and performs cleanup. It is intended to be run as a standalone script.

Main Steps:
1. Loads Hugging Face API token from .env and authenticates.
2. Downloads all files from the specified Hugging Face repo.
3. Checks for an existing BF16 GGUF file; if not found, runs conversion.
4. Adds metadata to the resulting GGUF file.
5. Cleans up cache directories to save disk space.

Usage:
    python download_convert.py <repo_id>

Arguments:
    repo_id: Hugging Face repository ID (e.g., google/gemma-3-1b-it)

Environment:
    Requires HF_API_TOKEN in .env file.

Functions:
    (None - all logic is in the main script body.)

Exits with code 0 on success, 1 on failure.
"""

import os
import subprocess
import argparse
from huggingface_hub import hf_hub_download, list_repo_files, login, HfApi
from dotenv import load_dotenv
import shutil
from update_readme import update_readme  # Import the update_readme function
from add_metadata_gguf import add_metadata
from pathlib import Path

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")
base_dir = os.path.expanduser("~/code/models")
run_dir = os.path.abspath("./")

if not api_token:
    print("Error: Hugging Face API token not found in .env file.")
    exit(1)  # Explicitly indicate failure

# Authenticate with the Hugging Face Hub
try:
    login(token=api_token)
    print("Authentication successful.")
except Exception as e:
    print(f"Authentication failed: {e}")
    exit(1)  # Explicitly indicate failure

# Parse arguments
parser = argparse.ArgumentParser(description="Download HF model and convert to BF16 GGUF")
parser.add_argument("repo_id", help="Hugging Face repository ID (e.g., google/gemma-3-1b-it)")
args = parser.parse_args()

repo_id = args.repo_id
llama_dir = os.path.expanduser("~/code/models/llama.cpp")

# Define the final BF16 file path
company_name, model_name = repo_id.split("/", 1)
output_dir = os.path.join(base_dir,model_name)
os.makedirs(output_dir, exist_ok=True)
bf16_output_file = os.path.join(output_dir, f"{model_name}-bf16.gguf")

# Check if the final BF16 file already exists
if os.path.exists(bf16_output_file):
    print(f"BF16 file already exists at {bf16_output_file}. Exiting.")
    exit(0)  # Success, no need to proceed further

# List all files in the repository
try:
    files = list_repo_files(repo_id=repo_id)
    print(f"Files found in repository '{repo_id}': {files}")
except Exception as e:
    print(f"Failed to list files in repository '{repo_id}': {e}")
    exit(1)  # Explicitly indicate failure

# Download each file
downloaded_files = []
try:
    for file_name in files:
        print(f"Downloading {file_name}...")
        try:
            file_path = hf_hub_download(repo_id=repo_id, filename=file_name, token=api_token)
            downloaded_files.append(file_path)
            print(f"Downloaded {file_name} to {file_path}")
        except Exception as e:
            print(f"Failed to download {file_name}: {e}")
            exit(1)  # Explicitly indicate failure
except Exception as e:
    print(f"An error occurred during the download process: {e}")
    exit(1)  # Explicitly indicate failure

# Download README.md if it exists
readme_path = None
for file_name in files:
    if file_name.lower() == "readme.md":
        print("Downloading README.md...")
        try:
            readme_path = hf_hub_download(repo_id=repo_id, filename=file_name, token=api_token)
            # Copy the README.md to the output directory
            readme_output_path = os.path.join(output_dir, "README.md")
            with open(readme_output_path, "wb") as f_out:
                with open(readme_path, "rb") as f_in:
                    f_out.write(f_in.read())
            print(f"README.md downloaded and saved to {readme_output_path}")
        except Exception as e:
            print(f"Failed to download README.md: {e}")
            exit(1)  # Explicitly indicate failure

# Identify main model file
bf16_model_path = None
for file_path in downloaded_files:
    if file_path.endswith(".gguf") and "bf16" in file_path:
        bf16_model_path = f"{output_dir}/{file_path}"
        break

if not bf16_model_path:
    print("No BF16-compatible model file found, converting...")
    model_snapshot_dir = os.path.dirname(downloaded_files[0])
    
    # Update the path to the convert_hf_to_gguf.py script
    convert_script_path = f"{llama_dir}/convert_hf_to_gguf.py"
    
    convert_command = [
        "python3", convert_script_path,
        model_snapshot_dir,
        "--outfile", bf16_output_file,
        "--model-name", model_name,
        "--outtype", "bf16"
    ]
    
    print("\nRunning conversion:", " ".join(convert_command))
    result = subprocess.run(convert_command, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"Successfully created BF16 GGUF: {bf16_output_file}")
    else:
        print("Error during conversion:")
        print(result.stderr)
        exit(1)  # Explicitly indicate failure

def convert_to_mmproj(convert_script_path, model_snapshot_dir, output_dir, model_name):
    """
    Attempt to convert to mmproj for each quant type.
    Failures are caught and reported, but do not stop the script.
    """
    mmproj_quant_types = ["f32", "f16", "bf16", "q8_0"]
    for quant_type in mmproj_quant_types:
        mmproj_output_file = os.path.join(output_dir, f"{model_name}-{quant_type}.mmproj")
        convert_command = [
            "python3", convert_script_path,
            model_snapshot_dir,
            "--outfile", mmproj_output_file,
            "--model-name", model_name,
            "--mmproj",
            "--outtype", quant_type
        ]
        print(f"\nAttempting mmproj conversion: {' '.join(convert_command)}")
        try:
            result = subprocess.run(convert_command, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Successfully created mmproj file: {mmproj_output_file}")
            else:
                print(f"mmproj conversion failed for {quant_type}: {result.stderr}")
        except Exception as e:
            print(f"Exception during mmproj conversion for {quant_type}: {e}")

# Add metadata using the imported function
metadata_failed = False
try:
    print("\nAdding metadata to the BF16 GGUF file...")
    add_metadata(bf16_output_file)  # Convert string to Path object
except Exception as e:
    print(f"Failed to add metadata: {e}")
    metadata_failed = True

# Try mmproj conversions (failures do not stop script)
try:
    convert_to_mmproj(convert_script_path, model_snapshot_dir, output_dir, model_name)
except Exception as e:
    print(f"Unexpected error during mmproj conversions: {e}")

# Delete the cache directory to save disk space after conversion
try:
    if model_snapshot_dir and os.path.exists(model_snapshot_dir):
        print(f"Cleaning up cache directory: {model_snapshot_dir}")
        shutil.rmtree(model_snapshot_dir)  # Delete the entire directory and its contents
        print(f"Cache directory {model_snapshot_dir} deleted successfully.")
except Exception as e:
    print(f"Error while deleting the cache directory: {e}")

if metadata_failed:
    print("Script completed with errors during metadata addition.")
else:
    print("Script completed successfully.")

# Exit with success (always 0, unless you want to propagate metadata failure)
exit(0)
