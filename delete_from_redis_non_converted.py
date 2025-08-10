import os
from dotenv import load_dotenv
from redis_utils import init_redis_catalog

# Load environment variables
load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
REDIS_USER = os.getenv("REDIS_USER", "admin")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

def main():
    catalog = init_redis_catalog(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        user=REDIS_USER,
        ssl=True
    )

    catalog_data = catalog.load_catalog()
    to_delete = [model_id for model_id, data in catalog_data.items()
                 if not data.get("converted", False)]

    print(f"Found {len(to_delete)} repos with converted=False.")
    if not to_delete:
        print("Nothing to delete.")
        return

    confirm = input(f"Delete these {len(to_delete)} repos from Redis? (y/n): ")
    if confirm.lower() != "y":
        print("Aborted.")
        return

    for model_id in to_delete:
        result = catalog.delete_model(model_id)
        print(f"{'Deleted' if result else 'Failed to delete'}: {model_id}")

    print("Done.")


if __name__ == "__main__":
    main()
