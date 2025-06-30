import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from huggingface_hub import HfApi
from dotenv import load_dotenv
import os
import sys
from make_files import get_model_size

from redis_utils import init_redis_catalog
from model_converter import ModelConverter

load_dotenv()

def get_model_catalog():
    REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
    REDIS_USER = os.getenv("REDIS_USER", "admin")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
    return init_redis_catalog(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user=REDIS_USER,
        ssl=True
    )

def add_enterprise_models_to_redis(enterprise_names):
    api = HfApi()
    catalog = get_model_catalog()
    converter = ModelConverter()
    for enterprise in enterprise_names:
        print(f"Checking models for enterprise: {enterprise}")
        try:
            models = api.list_models(author=enterprise)
        except Exception as e:
            print(f"Failed to list models for {enterprise}: {e}")
            continue
        for model in models:
            model_id = getattr(model, "modelId", None) or getattr(model, "id", None)
            if not model_id:
                continue
            if not catalog.get_model(model_id):
                print(f"Model not in Redis: {model_id} -- adding as not converted")
                # Use ModelConverter's logic for parameter and config detection (same as update_catalog)
                has_config = converter.has_config_json(model_id)
                parameters = model.get('config', {}).get('num_parameters') if hasattr(model, 'get') else None

                if parameters is None:
                    base_name = model_id.split('/')[-1]
                    parameters = get_model_size(base_name)

                if parameters is None or parameters == 0 or parameters == -1:
                    print(f"Estimating parameters via file size for {model_id}")
                    total_size = converter.get_file_sizes(model_id)
                    if total_size > 0:
                        parameters = converter.estimate_parameters(total_size)

                if parameters is None or parameters == 0:
                    print(f"Warning: {model_id} parameters could not be determined, setting to -1")
                    parameters = -1

                # Use ModelConverter's robust MoE detection (tries config and README)
                is_moe = converter.is_moe_model(model_id)
                from datetime import datetime
                new_entry = {
                    "added": datetime.now().isoformat(),
                    "parameters": parameters,
                    "has_config": has_config,
                    "converted": False,
                    "attempts": 0,
                    "last_attempt": None,
                    "success_date": None,
                    "error_log": [],
                    "quantizations": [],
                    "is_moe": is_moe
                }
                catalog.add_model(model_id, new_entry)
            else:
                print(f"Model already in Redis: {model_id}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python add_new_enterprise_models.py <enterprise1> [<enterprise2> ...]")
        exit(1)
    enterprise_names = sys.argv[1:]
    add_enterprise_models_to_redis(enterprise_names)
