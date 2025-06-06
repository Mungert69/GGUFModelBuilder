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

# Updated to match the exact formatting with bold markers
old_text = "(https://readyforquantum.com/download)"

# New text with same formatting
new_text = "(https://readyforquantum.com/download/?utm_source=github&utm_medium=referral&utm_campaign=huggingface_repo_readme)"

def update_readme(repo_id):
    print(f"\nProcessing repository: {repo_id}")
    
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
        
        print("\nCurrent README content preview:")
        print(content[:500] + "...\n")
        
        # Debug: Show exact match attempt
        print(f"Looking for EXACT text:\n{old_text}")
        
        # Check if the exact text exists
        if old_text in content:
            print("✅ Found EXACT matching text")
            
            # Replace the text
            new_content = content.replace(old_text, new_text)
            
            print("\nWill replace with:")
            print(new_text + "\n")
            
            # Ask for confirmation
            confirm = input("Do you want to proceed with this change? (y/n): ").lower()
            if confirm == 'y':
                # Upload the updated README
                api.upload_file(
                    path_or_fileobj=new_content.encode('utf-8'),
                    path_in_repo="README.md",
                    repo_id=repo_id,
                    token=api_token,
                )
                print(f"✅ Updated README in {repo_id}")
                return True
            else:
                print("❌ Update cancelled by user")
                return False
        else:
            print("❌ No matching text found in README")
            
            # Find the closest match
            similar_lines = [line for line in content.split('\n') if "FreeLLM" in line]
            if similar_lines:
                print("\nClosest matching lines found:")
                for i, line in enumerate(similar_lines, 1):
                    print(f"{i}. {line}")
            
            return False
            
    except Exception as e:
        print(f"❌ Error processing {repo_id}: {str(e)}")
        return False

def main():
    # Test with one specific repository
    test_repo = "Mungert/EXAONE-Deep-7.8B-GGUF"
    
    print(f"TEST MODE: Only processing {test_repo}")
    update_readme(test_repo)
    
    print("\nTest complete. Check the repository on huggingface.co to verify the changes.")

if __name__ == "__main__":
    main()
