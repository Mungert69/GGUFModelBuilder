import os
from dotenv import load_dotenv
from redis_utils import init_redis_catalog

load_dotenv()

def main():
    REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
    REDIS_USER = os.getenv("REDIS_USER", "admin")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    catalog = init_redis_catalog(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user=REDIS_USER,
        ssl=True
    )

    all_models = catalog.load_catalog()
    updated = 0
    already_converted = 0

    print(f"Loaded {len(all_models)} models from catalog.")
    for model_id, entry in all_models.items():
        converted = entry.get("converted", False)
        if not converted:
            print(f"Marking {model_id} as converted.")
            if catalog.update_model_field(model_id, "converted", True):
                updated += 1
        else:
            already_converted += 1

    print(f"\nDone. {updated} models updated.")
    print(f"{already_converted} models were already converted.")
    print(f"{len(all_models)} models in total.")

if __name__ == "__main__":
    main()