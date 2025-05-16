import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Any
import redis
from redis.exceptions import WatchError, RedisError

class RedisModelCatalog:
    def __init__(self, host: str, port: int, password: str, user: str, ssl: bool = True):
        """
        Initialize Redis connection for model catalog operations.
        
        Args:
            host: Redis server host
            port: Redis server port
            password: Redis password
            user: Redis user
            ssl: Whether to use SSL/TLS
        """
        self.r = redis.Redis(
            host=host,
            port=port,
            password=password,
            username=user,
            ssl=ssl,
            ssl_cert_reqs='none',  # Disable cert verification for testing
            ssl_check_hostname=False,  # <-- Add this line to fix the error
            decode_responses=True,
            retry_on_timeout=True,
            socket_keepalive=True
        )
        self.catalog_key = "model:catalog"
        self.converting_key = "model:converting"
        self.converting_progress_key = "model:converting:progress"
        self.converting_failed_key = "model:converting:failed"
        self.max_retries = 3

    def is_converting(self, model_id: str) -> bool:
        """Check if a model is currently being converted."""
        return self.r.sismember(self.converting_key, model_id)

    def unmark_converting(self, model_id: str):
        """Remove a model from the converting set. Optionally keep quant progress."""
        print(f"[RedisModelCatalog] unmark_converting: Removing '{model_id}' from converting set")
        self.r.srem(self.converting_key, model_id)

    def mark_converting(self, model_id: str) -> bool:
        """Mark a model as being converted. Returns True if marked, False if already present."""
        result = self.r.sadd(self.converting_key, model_id) == 1
        print(f"[RedisModelCatalog] mark_converting: Marked '{model_id}' as converting (added={result})")
        return result

    def mark_failed(self, model_id: str):
        """Mark a model as failed/interrupted (resumable)."""
        print(f"[RedisModelCatalog] mark_failed: Marked '{model_id}' as failed/resumable")
        self.r.sadd(self.converting_failed_key, model_id)

    def unmark_failed(self, model_id: str):
        """Remove a model from the failed set."""
        print(f"[RedisModelCatalog] unmark_failed: Removing '{model_id}' from failed set")
        self.r.srem(self.converting_failed_key, model_id)

    def is_failed(self, model_id: str) -> bool:
        """Check if a model is in the failed set."""
        return self.r.sismember(self.converting_failed_key, model_id)



    def get_converting_models(self):
        """Return a list of currently converting models."""
        return list(self.r.smembers(self.converting_key))
    
    def set_quant_progress(self, model_id: str, quant_name: str):
        """Set the current quantization step for a model."""
        self.r.hset(self.converting_progress_key, model_id, quant_name)

    def get_quant_progress(self, model_id: str) -> str:
        """Get the current quantization step for a model."""
        return self.r.hget(self.converting_progress_key, model_id)
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
        Returns:
            bool: True if field now matches desired value, False if failed
        """
        def _normalize_value(v):
            if isinstance(v, str):
                if v.lower() == 'true': return True
                if v.lower() == 'false': return False
                try: return json.loads(v.lower())
                except: return v
            return v

        def _update_operation():
            with self.r.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(self.catalog_key)
                        model_json = pipe.hget(self.catalog_key, model_id)
                        if not model_json:
                            print("Error: Model not found")
                            return False
                            
                        model = json.loads(model_json)
                        current_value = _normalize_value(model.get(field))
                        desired_value = _normalize_value(value)
                        
                        # If already matches, success!
                        if current_value == desired_value:
                            print(f"Field '{field}' already has desired value")
                            return True
                            
                        # Check conditions if provided
                        if condition:
                            for k, v in condition.items():
                                if _normalize_value(model.get(k)) != _normalize_value(v):
                                    print(f"Condition failed on field '{k}'")
                                    return False
                                    
                        # Perform update
                        model[field] = desired_value
                        pipe.multi()
                        pipe.hset(self.catalog_key, model_id, json.dumps(model))
                        pipe.execute()  # We don't actually care about the 0/1 response
                        return True
                        
                    except WatchError:
                        continue
                    except Exception as e:
                        print(f"Error during update: {str(e)}")
                        return False

        print(f"\nUpdating {model_id}.{field} → {value}")
        success = self._safe_operation(_update_operation)
        print(f"Operation {'succeeded' if success else 'failed'}\n")
        return success

    def delete_model(self, model_id: str) -> bool:
        """Delete a model from the catalog."""
        return self._safe_operation(lambda: self.r.hdel(self.catalog_key, model_id)) == 1

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

    def import_models_from_list(self, model_ids: list, defaults: Optional[dict] = None) -> dict:
        """
        Import multiple models from a list, marking them as converted.
        
        Args:
            model_ids: List of model IDs to import
            defaults: Optional default values for new models
            
        Returns:
            dict: Summary of operations {'added': x, 'updated': y}
        """
        if not defaults:
            defaults = {
                'converted': True,
                'added': datetime.now().isoformat(),
                'parameters': 0,
                'has_config': False,
                'attempts': 0,
                'error_log': [],
                'quantizations': [],
                "is_moe":False
            }
        
        added = 0
        updated = 0
        
        def _process_batch():
            nonlocal added, updated
            with self.r.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(self.catalog_key)
                        current_catalog = {
                            k: json.loads(v) 
                            for k, v in pipe.hgetall(self.catalog_key).items()
                        }
                        
                        for model_id in model_ids:
                            if model_id in current_catalog:
                                # Update existing if needed
                                if not current_catalog[model_id].get('converted', False):
                                    current_catalog[model_id]['converted'] = True
                                    updated += 1
                            else:
                                # Add new entry
                                current_catalog[model_id] = defaults.copy()
                                added += 1
                        
                        # Update Redis in one operation
                        pipe.multi()
                        pipe.delete(self.catalog_key)
                        if current_catalog:
                            for model_id, model_data in current_catalog.items():
                                pipe.hset(self.catalog_key, model_id, json.dumps(model_data))
                        pipe.execute()
                        break
                    except WatchError:
                        continue
        
        self._safe_operation(_process_batch)
        return {'added': added, 'updated': updated}

# Singleton instance (configure in your main script)
model_catalog = None

def init_redis_catalog(host: str, port: int, password: str, user: str , ssl: bool = True):
    """Initialize the global Redis catalog instance."""
    global model_catalog
    model_catalog = RedisModelCatalog(host, port, password, user,  ssl)
    return model_catalog

if __name__ == "__main__":
    import argparse
    import os

    # Load environment variables from .env if present
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # If python-dotenv is not installed, skip loading .env

    REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
    REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
    REDIS_USER = os.getenv("REDIS_USER", "admin")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

    parser = argparse.ArgumentParser(description="Redis Model Catalog CLI")
    parser.add_argument("--host", default=REDIS_HOST)
    parser.add_argument("--port", type=int, default=REDIS_PORT)
    parser.add_argument("--password", default=REDIS_PASSWORD)
    parser.add_argument("--user", default=REDIS_USER)
    parser.add_argument("--ssl", action="store_true", default=True)
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Add model command
    add_parser = subparsers.add_parser("add_model", help="Add a model to the catalog")
    add_parser.add_argument("--model_id", required=True)
    add_parser.add_argument("--model_info", required=True, help="JSON string of model info")

    # Get model command
    get_parser = subparsers.add_parser("get_model", help="Get a model from the catalog")
    get_parser.add_argument("--model_id", required=True)

    # Load catalog command
    load_parser = subparsers.add_parser("load_catalog", help="Load and print the entire catalog")

    # Update model field command
    update_parser = subparsers.add_parser("update_model_field", help="Update a field in a model")
    update_parser.add_argument("--model_id", required=True)
    update_parser.add_argument("--field", required=True)
    update_parser.add_argument("--value", required=True)
    update_parser.add_argument("--condition", help="JSON string of condition dict", default=None)

    # Increment counter command
    inc_parser = subparsers.add_parser("increment_counter", help="Increment a counter field")
    inc_parser.add_argument("--model_id", required=True)
    inc_parser.add_argument("--field", required=True)

    # Backup to file command
    backup_parser = subparsers.add_parser("backup_to_file", help="Backup catalog to a JSON file")
    backup_parser.add_argument("--file_path", required=True)

    # Initialize from file command
    init_parser = subparsers.add_parser("initialize_from_file", help="Initialize catalog from a JSON file")
    init_parser.add_argument("--file_path", required=True)

    # Import models from list command
    import_parser = subparsers.add_parser("import_models_from_list", help="Import models from a list")
    import_parser.add_argument("--model_ids", required=True, help="Comma-separated list of model IDs")
    import_parser.add_argument("--defaults", help="JSON string of default values", default=None)

    # Add mark_converting command
    mark_parser = subparsers.add_parser("mark_converting", help="Add a model ID to the converting set")
    mark_parser.add_argument("--model_id", required=True)

    args = parser.parse_args()
    catalog = init_redis_catalog(args.host, args.port, args.password, args.user, args.ssl)

    # Optional: Test connection before proceeding
    try:
        catalog.r.ping()
    except Exception as e:
        print(f"Could not connect to Redis: {e}")
        exit(1)

    import json

    if args.command == "add_model":
        model_info = json.loads(args.model_info)
        result = catalog.add_model(args.model_id, model_info)
        print("Added" if result else "Already exists or failed")
    elif args.command == "get_model":
        result = catalog.get_model(args.model_id)
        print(json.dumps(result, indent=2) if result else "Model not found")
    elif args.command == "load_catalog":
        result = catalog.load_catalog()
        print(json.dumps(result, indent=2))
    elif args.command == "update_model_field":
        value = json.loads(args.value) if args.value.startswith("{") or args.value.startswith("[") else args.value
        condition = json.loads(args.condition) if args.condition else None
        result = catalog.update_model_field(args.model_id, args.field, value, condition)
        print("Updated" if result else "Update failed")
    elif args.command == "increment_counter":
        result = catalog.increment_counter(args.model_id, args.field)
        print("Incremented" if result else "Increment failed")
    elif args.command == "backup_to_file":
        result = catalog.backup_to_file(args.file_path)
        print("Backup successful" if result else "Backup failed")
    elif args.command == "initialize_from_file":
        result = catalog.initialize_from_file(args.file_path)
        print("Initialization successful" if result else "Initialization failed")
    elif args.command == "import_models_from_list":
        model_ids = [mid.strip() for mid in args.model_ids.split(",")]
        defaults = json.loads(args.defaults) if args.defaults else None
        result = catalog.import_models_from_list(model_ids, defaults)
        print(json.dumps(result, indent=2))
    elif args.command == "mark_converting":
        result = catalog.mark_converting(args.model_id)
        print("Added to converting set" if result else "Already in converting set")
    else:
        print("Unknown command")
