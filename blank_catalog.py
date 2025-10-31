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

    # Delete the entire model:catalog hash
    deleted = catalog.r.delete(catalog.catalog_key)
    print(f"Deleted catalog: {deleted} (1 means success, 0 means already empty)")

if __name__ == "__main__":
    main()
