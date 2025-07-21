import os
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
from redis_utils import init_redis_catalog

# Load environment variables
load_dotenv()
api_token = os.getenv("HF_API_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
REDIS_USER = os.getenv("REDIS_USER", "admin")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

if not api_token:
    print("Error: Hugging Face API token not found in .env file.")
    exit(1)

# Authenticate with Hugging Face
login(token=api_token)
api = HfApi()

# Initialize Redis catalog
catalog = init_redis_catalog(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    user=REDIS_USER,
    ssl=True
)

import re

def strip_gguf_suffix(name):
    # Remove -GGUF or -gguf (case-insensitive) from the end of the name
    return re.sub(r'(?i)-gguf$', '', name)

def map_author_models_to_originals(author):
    """
    For each model in the author's namespace, find the original model (from any user/org)
    that matches the base name (with -GGUF suffix removed). Returns a dict mapping author model id -> original model id.
    """
    print(f"Fetching all models for author '{author}'...")
    author_repos = list(api.list_models(author=author))
    base_names = [strip_gguf_suffix(repo.id.split("/")[-1]) for repo in author_repos]
    print(f"Found {len(base_names)} base names for author (after stripping -GGUF).")

    mapping = {}
    for repo in author_repos:
        author_model_id = repo.id
        base_name = strip_gguf_suffix(author_model_id.split("/")[-1])
        # Use the search API to find models with this base name
        search_results = list(api.list_models(search=base_name, limit=10))
        # Try to find an exact match on the base name
        found = False
        for result in search_results:
            if strip_gguf_suffix(result.id.split("/")[-1]) == base_name and result.id != author_model_id:
                mapping[author_model_id] = result.id
                found = True
                break
        if not found:
            print(f"Warning: Could not resolve original model for base name '{base_name}' (author model: {author_model_id})")
    return mapping

def write_models_to_redis(model_ids):
    """
    Write the given model IDs to Redis, marking them as converted.
    """
    result = catalog.import_models_from_list(model_ids, defaults={"converted": True})
    print(f"Added: {result['added']}, Updated: {result['updated']}")

if __name__ == "__main__":
    # Set your author here
    author = "Mungert"
    mapping = map_author_models_to_originals(author)
    print("Author model -> Original model mapping:")
    for k, v in mapping.items():
        print(f"{k} -> {v}")
    # Write only the original model ids to Redis
    original_model_ids = list(mapping.values())
    write_models_to_redis(original_model_ids)
