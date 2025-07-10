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

# Set your model prefix and collection name here
MODEL_PREFIX = "mungert/granite"
COLLECTION_NAME = "granite-models"

# 1. List all your models that start with the prefix
all_models = list(api.list_models(author="mungert"))
matching_models = [m.id for m in all_models if m.id.startswith(MODEL_PREFIX)]

if not matching_models:
    print(f"No models found with prefix '{MODEL_PREFIX}'")
    exit()

print(f"Found {len(matching_models)} models with prefix '{MODEL_PREFIX}':")
for m in matching_models:
    print(f" - {m}")

# 2. Check if the collection exists
collections = list(api.list_collections())
collection = next((c for c in collections if c.id == f"mungert/{COLLECTION_NAME}"), None)

# 3. Create the collection if it doesn't exist
if not collection:
    print(f"Collection '{COLLECTION_NAME}' does not exist. Creating it...")
    api.create_collection(
        name=COLLECTION_NAME,
        description=f"Collection of models starting with {MODEL_PREFIX}",
        private=False,
    )
    print(f"Collection '{COLLECTION_NAME}' created.")
else:
    print(f"Collection '{COLLECTION_NAME}' already exists.")

# 4. Add all matching models to the collection
for model_id in matching_models:
    try:
        api.add_to_collection(
            collection_id=f"mungert/{COLLECTION_NAME}",
            model_id=model_id,
        )
        print(f"Added {model_id} to collection '{COLLECTION_NAME}'")
    except Exception as e:
        print(f"Failed to add {model_id}: {e}")

print("Done.")
