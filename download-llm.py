from huggingface_hub import hf_hub_download, list_repo_files, login
from dotenv import load_dotenv
import os

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

# Get the repository ID from the user
repo_id = input("Enter the Hugging Face repository ID: ")

# List all files in the repository
try:
    files = list_repo_files(repo_id=repo_id)
    print(f"Files found in repository '{repo_id}': {files}")
except Exception as e:
    print(f"Failed to list files in repository '{repo_id}': {e}")
    exit()

# Download each file
try:
    for file_name in files:
        print(f"Downloading {file_name}...")
        try:
            file_path = hf_hub_download(repo_id=repo_id, filename=file_name, token=api_token)
            print(f"Downloaded {file_name} to {file_path}")
        except Exception as e:
            print(f"Failed to download {file_name}: {e}")
except Exception as e:
    print(f"An error occurred during the download process: {e}")

