import os
import subprocess
import argparse
from huggingface_hub import hf_hub_download, list_repo_files, login, HfApi
from dotenv import load_dotenv
import shutil
from update_readme import update_readme  # Import the update_readme function

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")

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
parser.add_argument("output_dir", help="Directory to store downloaded and converted files")
args = parser.parse_args()

repo_id = args.repo_id
output_dir = os.path.abspath(args.output_dir)
os.makedirs(output_dir, exist_ok=True)

# Define the final BF16 file path
model_base_name = repo_id.split("/")[-1]
bf16_output_file = os.path.join(output_dir, f"{model_base_name}-bf16.gguf")

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
        bf16_model_path = file_path
        break

if not bf16_model_path:
    print("No BF16-compatible model file found, converting...")
    model_snapshot_dir = os.path.dirname(downloaded_files[0])
    
    # Update the path to the convert_hf_to_gguf.py script
    convert_script_path = "./llama.cpp/convert_hf_to_gguf.py"
    
    convert_command = [
        "python3", convert_script_path,
        model_snapshot_dir,
        "--outfile", bf16_output_file,
        "--model-name", model_base_name,
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

# Delete the cache directory to save disk space after conversion
if model_snapshot_dir and os.path.exists(model_snapshot_dir):
    try:
        print(f"Cleaning up cache directory: {model_snapshot_dir}")
        shutil.rmtree(model_snapshot_dir)  # Delete the entire directory and its contents
        print(f"Cache directory {model_snapshot_dir} deleted successfully.")
    except Exception as e:
        print(f"Error while deleting the cache directory: {e}")

# Update README.md after BF16 creation
update_readme(output_dir, model_base_name)

# Exit with success
exit(0)
