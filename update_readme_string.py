from huggingface_hub import HfApi, login
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

# Initialize API
api = HfApi()

# Text patterns
old_text = "🔵 **FreeLLM** – Runs **open-source Hugging Face models** Medium speed (unlimited, subject to Hugging Face API availability)."
new_text = "🔵 **HugLLM** – Runs **open-source Hugging Face models** Fast, Runs small models (≈8B) hence lower quality, Get 2x more tokens (subject to Hugging Face API availability)"

def update_readme(repo_id, require_confirmation=True):
    try:
        # Get the README content
        readme_path = api.hf_hub_download(
            repo_id=repo_id,
            filename="README.md",
            token=api_token,
            repo_type="model"
        )
        
        # Read the content
        with open(readme_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if old_text in content:
            if require_confirmation:
                print(f"\nFirst model found: {repo_id}")
                print("\nCurrent text:")
                print(old_text)
                print("\nWill replace with:")
                print(new_text)
                
                confirm = input("\nProceed with this change and update ALL similar models? (y/n): ").lower()
                if confirm != 'y':
                    print("Update cancelled by user")
                    return False, 0
            
            # Replace the text
            new_content = content.replace(old_text, new_text)
            
            # Upload the updated README
            api.upload_file(
                path_or_fileobj=new_content.encode('utf-8'),
                path_in_repo="README.md",
                repo_id=repo_id,
                token=api_token,
            )
            return True, 1
        return False, 0
            
    except Exception as e:
        print(f"❌ Error processing {repo_id}: {str(e)}")
        return False, 0

def main():
    # List all model repositories (converting generator to list)
    repos = list(api.list_models(author="Mungert"))
    print(f"Found {len(repos)} repositories to check")
    
    # First pass - find first matching model and get confirmation
    confirmed = False
    total_updated = 0
    
    for repo in repos:
        success, count = update_readme(repo.id, require_confirmation=not confirmed)
        total_updated += count
        
        if success and not confirmed:
            confirmed = True
            print("\nConfirmation received. Updating remaining models automatically...")
            continue
        
        if confirmed and not success:
            print(f"⏩ No match in {repo.id} - skipping")
    
    print(f"\nUpdate complete! Successfully updated {total_updated} repositories.")

if __name__ == "__main__":
    main()
