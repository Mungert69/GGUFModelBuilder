import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Any
import redis
from redis.exceptions import WatchError, RedisError

class RedisModelCatalog:
    def __init__(self, host: str, port: int, password: str, ssl: bool = True):
        """
        Initialize Redis connection for model catalog operations.
        
        Args:
            host: Redis server host
            port: Redis server port
            password: Redis password
            ssl: Whether to use SSL/TLS
        """
        self.r = redis.Redis(
            host=host,
            port=port,
            password=password,
            ssl=ssl,
            ssl_cert_reqs='none',  # Disable cert verification for testing
            decode_responses=True,
            retry_on_timeout=True,
            socket_keepalive=True
        )
        self.catalog_key = "model:catalog"
        self.max_retries = 3

    def _safe_operation(self, operation, *args, **kwargs):
        """Helper for retrying failed operations."""
        for attempt in range(self.max_retries):
            try:
                return operation(*args, **kwargs)
            except (WatchError, RedisError) as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(0.1 * (attempt + 1))
        return None

    def load_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Load entire catalog from Redis."""
        try:
            catalog = self.r.hgetall(self.catalog_key)
            return {k: json.loads(v) for k, v in catalog.items()}
        except (json.JSONDecodeError, RedisError) as e:
            logging.error(f"Error loading catalog: {e}")
            return {}

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Get single model entry."""
        model_json = self.r.hget(self.catalog_key, model_id)
        return json.loads(model_json) if model_json else None

    def add_model(self, model_id: str, model_info: Dict[str, Any]) -> bool:
        """
        Add a new model to the catalog atomically.
        
        Args:
            model_id: The model identifier (e.g. "allenai/olmOCR-7B-0225-preview")
            model_info: Dictionary of model attributes
            
        Returns:
            bool: True if successfully added, False if model already exists
        """
        def _add_operation():
            with self.r.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(self.catalog_key)
                        if pipe.hexists(self.catalog_key, model_id):
                            return False
                        
                        pipe.multi()
                        pipe.hset(self.catalog_key, model_id, json.dumps(model_info))
                        return pipe.execute()[0]
                    except WatchError:
                        continue

        return self._safe_operation(_add_operation) or False

    def update_model_field(
        self,
        model_id: str,
        field: str,
        value: Any,
        condition: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update a specific field in a model entry with optional conditions.
        
        Args:
            model_id: The model identifier
            field: Field name to update
            value: New value
            condition: Optional dictionary of field/value pairs that must match current values
            
        Returns:
            bool: True if update succeeded
        """
        def _update_operation():
            with self.r.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(self.catalog_key)
                        model_json = pipe.hget(self.catalog_key, model_id)
                        if not model_json:
                            return False
                            
                        model = json.loads(model_json)
                        
                        # Check conditions if provided
                        if condition:
                            for k, v in condition.items():
                                if model.get(k) != v:
                                    return False
                                    
                        # Update the field
                        model[field] = value
                        
                        pipe.multi()
                        pipe.hset(self.catalog_key, model_id, json.dumps(model))
                        return pipe.execute()[0]
                    except WatchError:
                        continue

        return self._safe_operation(_update_operation) or False

    def increment_counter(self, model_id: str, field: str) -> bool:
        """Atomically increment a counter field."""
        return self._safe_operation(
            lambda: self.r.hincrby(self.catalog_key, f"{model_id}:{field}", 1)
        )

    def backup_to_file(self, file_path: str) -> bool:
        """Create a backup of the catalog to JSON file."""
        try:
            catalog = self.load_catalog()
            with open(file_path, 'w') as f:
                json.dump(catalog, f, indent=2)
            return True
        except Exception as e:
            logging.error(f"Backup failed: {e}")
            return False

    def initialize_from_file(self, file_path: str) -> bool:
        """Initialize Redis catalog from JSON file."""
        try:
            with open(file_path) as f:
                catalog = json.load(f)
            
            with self.r.pipeline() as pipe:
                for model_id, data in catalog.items():
                    pipe.hset(self.catalog_key, model_id, json.dumps(data))
                pipe.execute()
            return True
        except Exception as e:
            logging.error(f"Initialization failed: {e}")
            return False


# Singleton instance (configure in your main script)
model_catalog = None

def init_redis_catalog(host: str, port: int, password: str, ssl: bool = True):
    """Initialize the global Redis catalog instance."""
    global model_catalog
    model_catalog = RedisModelCatalog(host, port, password, ssl)
    return model_catalog
