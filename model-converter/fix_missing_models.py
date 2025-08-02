import os
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("sys.path:", sys.path)
print("Parent dir contents:", os.listdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))
from redis_utils import init_redis_catalog
from make_files import get_model_size
from model_converter import ModelConverter

# Only instantiate ModelConverter once
def get_model_converter():
    if not hasattr(get_model_converter, "_instance"):
        get_model_converter._instance = ModelConverter()
    return get_model_converter._instance

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
from datetime import datetime

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



def get_parameters_and_moe_for_model(model_id, api):
    """
    Try to get the number of parameters and MoE status for a model using config, name, or file size.
    """
    converter = get_model_converter()
    # 1. Try config
    params = None
    try:
        info = api.model_info(model_id)
        if "num_parameters" in info.config:
            params = int(info.config["num_parameters"])
    except Exception as e:
        print(f"[WARN] Could not get num_parameters from config for {model_id}: {e}")

    # 2. Try name-based estimation
    if not params:
        base_name = model_id.split("/")[-1]
        params = get_model_size(base_name)

    # 3. Try file size estimation (using ModelConverter logic)
    if not params or params <= 0:
        try:
            total_size = converter.get_file_sizes(model_id)
            if total_size > 0:
                params = int(converter.estimate_parameters(total_size))
        except Exception as e:
            print(f"[WARN] Could not estimate parameters from file size for {model_id}: {e}")

    if not params or params <= 0:
        params = -1

    # MoE detection
    try:
        is_moe = converter.check_moe_from_config(model_id)
    except Exception as e:
        print(f"[WARN] Could not check MoE for {model_id}: {e}")
        is_moe = False

    return params, is_moe

def write_models_to_redis(model_ids):
    """
    Write the given model IDs to Redis, marking them as converted and filling in parameters, is_moe, conversion_date, and has_config.
    """
    enriched_models = []
    now = datetime.now().isoformat()
    for model_id in model_ids:
        params, is_moe = get_parameters_and_moe_for_model(model_id, api)
        enriched_models.append({
            "model_id": model_id,
            "converted": True,
            "parameters": params if params > 0 else -1,
            "is_moe": is_moe,
            "conversion_date": now,
            "has_config": True
        })
    result = catalog.import_models_from_list(
        [m["model_id"] for m in enriched_models],
        defaults={"converted": True, "conversion_date": now, "has_config": True}
    )
    print(f"Added: {result['added']}, Updated: {result['updated']}")
    for m in enriched_models:
        catalog.update_model_field(m["model_id"], "parameters", m["parameters"])
        catalog.update_model_field(m["model_id"], "is_moe", m["is_moe"])
        catalog.update_model_field(m["model_id"], "conversion_date", m["conversion_date"])
        catalog.update_model_field(m["model_id"], "has_config", True)

if __name__ == "__main__":
    # Set your author here
    with open(os.path.join(os.path.dirname(__file__), "username"), "r") as f:
        author = f.read().strip()
    mapping = map_author_models_to_originals(author)
    print("Author model -> Original model mapping:")
    for k, v in mapping.items():
        print(f"{k} -> {v}")
    # Write only the original model ids to Redis
    original_model_ids = list(mapping.values())
    write_models_to_redis(original_model_ids)
