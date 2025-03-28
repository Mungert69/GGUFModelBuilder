import os
import shutil
from huggingface_hub import HfApi, login
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
HF_TOKEN = os.getenv("HF_API_TOKEN")

# Configuration
TARGET_DIR = "/home/mahadeva/code/models/imatrix-files"
REPO_OWNER = "Mungert"  # Your username/organization
FILE_EXTENSION = ".imatrix"

def ensure_target_dir():
    """Create target directory if it doesn't exist"""
    os.makedirs(TARGET_DIR, exist_ok=True)
    print(f"Target directory: {TARGET_DIR}")

def get_all_repos():
    """Fetch all repositories for the specified owner using correct API method"""
    api = HfApi()
    models = api.list_models(author=REPO_OWNER)
    return [model.modelId for model in models if "-GGUF" in model.modelId]

def download_imatrix_files(repo_id):
    """Download imatrix files from a repository"""
    api = HfApi()
    try:
        files = api.list_repo_files(repo_id)
        imatrix_files = [f for f in files if f.endswith(FILE_EXTENSION)]
        
        if not imatrix_files:
            print(f"No imatrix files found in {repo_id}")
            return
        
        print(f"\nFound {len(imatrix_files)} imatrix file(s) in {repo_id}:")
        
        for file in imatrix_files:
            # Extract model name (assuming format: modelname-GGUF/modelname.imatrix)
            model_name = file.split('/')[-1].replace(FILE_EXTENSION, "")
            target_path = os.path.join(TARGET_DIR, f"{model_name}{FILE_EXTENSION}")
            
            if os.path.exists(target_path):
                print(f"✓ Already exists: {model_name}{FILE_EXTENSION}")
                continue
            
            print(f"↓ Downloading: {file}")
            try:
                downloaded_file = api.hf_hub_download(
                    repo_id=repo_id,
                    filename=file,
                    local_dir=TARGET_DIR,
                    local_dir_use_symlinks=False,
                    token=HF_TOKEN
                )
                print(f"✓ Saved to: {downloaded_file}")
            except Exception as e:
                print(f"✗ Failed to download {file}: {str(e)}")
                
    except Exception as e:
        print(f"Error processing {repo_id}: {str(e)}")

def main():
    # Authenticate
    try:
        login(token=HF_TOKEN)
        print("Authentication successful")
    except Exception as e:
        print(f"Authentication failed: {str(e)}")
        return
    
    ensure_target_dir()
    
    print(f"\nFetching repositories for {REPO_OWNER}...")
    repos = get_all_repos()
    
    if not repos:
        print("No GGUF repositories found")
        return
    
    print(f"Found {len(repos)} GGUF repositories:")
    for repo in repos:
        print(f" - {repo}")
    
    print("\nStarting download process...")
    for repo in repos:
        download_imatrix_files(repo)
    
    print("\nAll imatrix files processed!")

if __name__ == "__main__":
    main()
