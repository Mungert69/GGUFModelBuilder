from huggingface_hub import HfApi, login
from dotenv import load_dotenv
import os
import argparse
import shutil

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
parser = argparse.ArgumentParser(description="Upload files to Hugging Face and delete them upon successful upload.")
parser.add_argument("repo_id", help="Hugging Face repository ID (e.g., Mungert/gemma-3-12b-it-GGUF)")
parser.add_argument("upload_dir", help="Directory containing the files to upload")
args = parser.parse_args()

repo_id = args.repo_id
upload_dir = args.upload_dir

# Initialize API
api = HfApi()

# Create repository if it doesn't exist
try:
    api.create_repo(repo_id, exist_ok=True, token=api_token)
    print(f"Repository {repo_id} is ready.")
except Exception as e:
    print(f"Error creating repository: {e}")
    exit()

# Upload README.md if it exists
readme_path = os.path.join(upload_dir, "README.md")
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

# Upload all other files in the directory and delete them upon successful upload
try:
    for file_name in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, file_name)
        if os.path.isfile(file_path) and file_name != "README.md":
            print(f"Uploading {file_name}...")
            try:
                api.upload_file(
                    path_or_fileobj=file_path,
                    path_in_repo=file_name,  # Change this if you want a subdirectory in the repo
                    repo_id=repo_id,
                    token=api_token,
                )
                print(f"Uploaded {file_name} successfully.")
                # Delete the file only if the upload succeeds
                os.remove(file_path)
                print(f"Deleted {file_name} locally.")
            except Exception as e:
                print(f"Error uploading {file_name}: {e}")
except Exception as e:
    print(f"An error occurred during the upload process: {e}")

print("Upload and cleanup completed successfully.")
