
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("sys.path:", sys.path)
print("Parent dir contents:", os.listdir(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))

from redis_utils import init_redis_catalog

# Load environment variables (if using dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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

catalog_data = catalog.load_catalog()
print(f"Loaded {len(catalog_data)} models from catalog.")

for model_id in catalog_data:
    print(f"Resetting attempts for {model_id}")
    catalog.update_model_field(model_id, "attempts", 0)

print("All model attempts have been reset to 0.")

