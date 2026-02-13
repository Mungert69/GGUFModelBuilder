
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("sys.path:", sys.path)
print("Parent dir contents:", os.listdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))
from dotenv import load_dotenv
from redis_utils import init_redis_catalog

load_dotenv()

def main():
    REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
    REDIS_USER = os.getenv("REDIS_USER", "admin")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    model_catalog = init_redis_catalog(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user=REDIS_USER,
        ssl=True
    )

    catalog = model_catalog.load_catalog()
    to_delete = []
    for model_id, entry in catalog.items():
        parameters = entry.get("parameters", None)
        has_config = entry.get("has_config", True)
        try:
            parameters = float(parameters)
        except (ValueError, TypeError):
            parameters = -1

        if parameters == -1 or not has_config:
            to_delete.append(model_id)

    print(f"Found {len(to_delete)} bad models to delete.")
    for model_id in to_delete:
        print(f"Deleting {model_id} (parameters={catalog[model_id].get('parameters')}, has_config={catalog[model_id].get('has_config')})")
        model_catalog.delete_model(model_id)

    print("Done.")

if __name__ == "__main__":
    main()

