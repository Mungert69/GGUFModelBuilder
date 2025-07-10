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

# Ask user for collection slug, display name, and model name prefix
import re
account_name = input("Enter your HuggingFace username (case-sensitive, e.g. 'Mungert'): ").strip()
collection_slug = input("Enter the collection slug (no spaces, lowercase, e.g. 'granite-models'): ").strip()
collection_display_name = input("Enter the collection display name (can have spaces, e.g. 'Granite Models'): ").strip()
model_name_prefix = input("Enter the model name prefix (e.g. 'granite'): ").strip()

# 1. List all your models whose model name starts with the prefix (case-insensitive)
print(f"Fetching models for user '{account_name}' from Hugging Face Hub...")
all_models = list(api.list_models(author=account_name))
print(f"Fetched {len(all_models)} models. Filtering by prefix...")

matching_models = [
    m.id for m in all_models
    if m.id.split("/", 1)[1].lower().startswith(model_name_prefix.lower())
]

if not matching_models:
    print(f"No models found in account '{account_name}' with model name starting with '{model_name_prefix}'")
    exit()

print(f"Found {len(matching_models)} models in '{account_name}/' with model name starting with '{model_name_prefix}':")
for m in matching_models:
    print(f" - {m}")

# 2. Check if the collection exists
collections = list(api.list_collections())
collection_id = f"{account_name}/{collection_slug}"
collection = next((c for c in collections if c.id == collection_id), None)

# 3. Create the collection if it doesn't exist
if not collection:
    print(f"Collection '{collection_slug}' does not exist. Creating it...")
    try:
        api.create_collection(
            name=collection_slug,
            title=collection_display_name,
            description=f"Collection of models starting with {model_name_prefix}",
            private=False,
        )
        print(f"Collection '{collection_display_name}' (slug: '{collection_slug}') created.")
    except Exception as e:
        print(f"Failed to create collection: {e}")
        exit()
else:
    print(f"Collection '{collection_display_name}' (slug: '{collection_slug}') already exists.")

# 4. Add all matching models to the collection
import time

for idx, model_id in enumerate(matching_models, 1):
    print(f"Adding model {idx}/{len(matching_models)}: {model_id} ...", end="")
    try:
        api.add_to_collection(
            collection_id=collection_id,
            model_id=model_id,
        )
        print(" done.")
    except Exception as e:
        print(f" failed: {e}")
    time.sleep(0.5)  # Add a short delay to avoid rate limits

print("All models processed. Done.")
