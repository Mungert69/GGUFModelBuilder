from huggingface_hub import HfApi, login
from dotenv import load_dotenv
import os
import argparse
import shutil
from make_files import upload_large_file , extract_quant_folder_name 

base_dir = os.path.expanduser("~/code/models")

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")

if not api_token:
    print("Error: Hugging Face API token not found in .env file.")
    exit()

# Authenticate with the Hugging Face Hub
try:
    login(token=api_token)
    print("Authentication successful.")
except Exception as e:
    print(f"Authentication failed: {e}")
    exit()

# Parse arguments
parser = argparse.ArgumentParser(description="Upload quantized GGUF model files to Hugging Face and clean up")
parser.add_argument("model_name", help="Base name of the model (e.g., gemma-3-12b-it)")
args = parser.parse_args()

model_base = args.model_name

# Hugging Face repo ID (adjust as needed)
repo_id = f"Mungert/{model_base}-GGUF"

# Directory containing the files to upload (matches model name folder from quantization script)
upload_dir = os.path.join(base_dir, model_base)

# Hugging Face cache directory
hf_cache_dir = os.path.expanduser("~/.cache/huggingface/hub/")

# Initialize API
api = HfApi()

# Upload all files in the directory except README.md
try:
    for file_name in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, file_name)
        if os.path.isfile(file_path) :
            print(f"Uploading {file_name}...")
            quant_type=extract_quant_folder_name(file_name);
            upload_large_file(file_path, repo_id, quant_type)
            print(f"Uploaded {file_name} successfully.")
except Exception as e:
    print(f"An error occurred during the upload process: {e}")

# Cleanup: Remove the local model directory
if os.path.exists(upload_dir):
    try:
        print(f"Deleting local model directory: {upload_dir}")
        shutil.rmtree(upload_dir)
        print("Model directory deleted successfully.")
    except Exception as e:
        print(f"Error deleting model directory: {e}")

# Cleanup: Clear Hugging Face cache
if os.path.exists(hf_cache_dir):
    try:
        print(f"Clearing Hugging Face cache: {hf_cache_dir}")
        shutil.rmtree(hf_cache_dir)
        os.makedirs(hf_cache_dir, exist_ok=True)  # Recreate an empty folder
        print("Hugging Face cache cleared successfully.")
    except Exception as e:
        print(f"Error clearing Hugging Face cache: {e}")
else:
    print("Hugging Face cache folder does not exist. Nothing to clear.")

print("Upload and cleanup completed successfully.")
