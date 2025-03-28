import os
import sys
from huggingface_hub import HfApi

# Check if at least two arguments are provided (repo ID and at least one file)
if len(sys.argv) < 3:
    print("Usage: python delete_from_hf.py <repo_id> <file1> [<file2> ...]")
    sys.exit(1)

# Extract repo ID from arguments
repo_id = sys.argv[1]

# Extract file list
files_to_delete = sys.argv[2:]

# Hugging Face API token (ensure it's set in your environment)
api_token = os.getenv("HF_API_TOKEN")

# Initialize API
api = HfApi()

# Loop through files passed as arguments and delete them
for file_to_delete in files_to_delete:
    try:
        api.delete_file(path_in_repo=file_to_delete, repo_id=repo_id, token=api_token)
        print(f"Successfully deleted {file_to_delete} from {repo_id}.")
    except Exception as e:
        print(f"Error deleting {file_to_delete}: {e}")

