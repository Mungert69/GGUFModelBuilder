import os
import json
import time
import requests
import subprocess
import threading
import sys
import shutil
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from make_files import get_model_size
from huggingface_hub import HfApi, HfFileSystem, login
from build_llama import build_and_copy
from redis_utils import init_redis_catalog

load_dotenv()

class ModelConverter:

    def __init__(self):
        # Initialize Redis connection
        REDIS_HOST = os.getenv("REDIS_HOST", "redis.freenetworkmonitor.click")
        REDIS_PORT = int(os.getenv("REDIS_PORT", "46379"))
        REDIS_USER = os.getenv("REDIS_USER", "admin")
        REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
        
        self.model_catalog = init_redis_catalog(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            user=REDIS_USER,
            ssl=True
        )
        
        # Test Redis connection
        try:
            ping_response = self.model_catalog.r.ping()
            print(f"Redis connection test: {'Success' if ping_response else 'Failed'}")
        except Exception as e:
            print(f"Redis connection failed: {e}")
            exit(1)

        self.hf_token = os.getenv("HF_API_TOKEN")
        self.MAX_PARAMETERS = 9e9  # 9 billion parameters
        self.MAX_ATTEMPTS = 3        
        self.HF_CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")
        # Authenticate with Hugging Face Hub
        if not self.hf_token:
            print("Error: Hugging Face API token not found in .env file.")
            exit()
        try:
            login(token=self.hf_token)
            print("Authentication successful.")
        except Exception as e:
            print(f"Authentication failed: {e}")
            exit()
        
        self.api = HfApi()
        self.fs = HfFileSystem()
    def run_script(self, script_name, args):
        """Runs a script with arguments and streams output in real time.
        Returns True if the script succeeds, False otherwise."""
        script_path = os.path.join(os.getcwd(), script_name)  # Ensure absolute path
        if not os.path.exists(script_path):
            print(f"Error: Script {script_name} not found at {script_path}")
            return False  # Indicate failure

        print(f"\nRunning {script_name} with arguments: {args}")

        # Run the script with real-time output streaming
        process = subprocess.Popen(
            ["python3", script_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=-1,  # Use default buffering
            universal_newlines=False  # Read output as raw bytes
        )

        # Function to read and print output in real time
        def read_output(pipe, is_stderr=False):
            for line in iter(pipe.readline, b''):  # Read bytes
                if is_stderr:
                    sys.stderr.buffer.write(line)  # Write binary to stderr
                else:
                    sys.stdout.buffer.write(line)  # Write binary to stdout
                sys.stdout.flush()
            pipe.close()

        # Start threads to read stdout and stderr
        stdout_thread = threading.Thread(target=read_output, args=(process.stdout,))
        stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True))
        stdout_thread.start()
        stderr_thread.start()

        # Wait for the process to complete
        process.wait()
        stdout_thread.join()
        stderr_thread.join()

        exit_code = process.returncode
        if exit_code != 0:
            print(f"\nError running {script_name}, exited with code {exit_code}")
            return False  # Indicate failure
        else:
            print(f"Successfully ran {script_name}")
            return True  # Indicate success

    def load_catalog(self):
        """Load catalog from Redis"""
        return self.model_catalog.load_catalog()

    def save_catalog(self, catalog=None):
        """Save catalog to Redis (no-op since Redis updates are immediate)"""
        pass  # Redis updates are done immediately through model_catalog methods

    def estimate_parameters(self, file_size):
        """Estimate the number of parameters based on file size."""
        if file_size == 0:
            return 0

        estimated_params_fp32 = file_size / 4
        estimated_params_fp16 = file_size / 2

        print(f"Estimated parameters (FP32): {estimated_params_fp32}, (FP16/BF16): {estimated_params_fp16}")
        return estimated_params_fp32

    def get_file_sizes(self, model_id):
        """Get the total size of .safetensors files in the repository."""
        try:
            print(f"\n[DEBUG] Starting file size check for: {model_id}")
            
            try:
                repo_info = self.api.repo_info(model_id, repo_type="model")
                print(f"[DEBUG] Repository found: {repo_info.id}")
            except Exception as repo_err:
                print(f"[ERROR] Repository not found or inaccessible: {model_id}")
                print(f"[ERROR] Details: {str(repo_err)}")
                return 0

            try:
                paths_to_check = [
                    f"models/{model_id}",
                    f"datasets/{model_id}",
                    f"{model_id}",
                ]

                total_size = 0
                found_files = False

                for path in paths_to_check:
                    print(f"[DEBUG] Checking path: {path}")
                    try:
                        files = self.fs.ls(path, detail=True)
                        print(f"[DEBUG] Found {len(files)} files in {path}:")
                        for f in files:
                            print(f" - {f['name']} ({f['size']} bytes)")
                        
                        safetensors_files = [f for f in files if f['name'].endswith('.safetensors')]
                        if safetensors_files:
                            found_files = True
                            total_size += sum(f['size'] for f in safetensors_files)
                    except Exception as ls_err:
                        print(f"[DEBUG] Failed to list files in {path}: {str(ls_err)}")
                        return 0

                if not found_files:
                    print(f"[WARNING] No .safetensors files found for {model_id}")
                    return 0

                print(f"[DEBUG] Total .safetensors size: {total_size} bytes")
                return total_size

            except Exception as fs_err:
                print(f"[ERROR] Failed to list or sum file sizes: {str(fs_err)}")
                return 0

        except Exception as e:
            print(f"[ERROR] File size check failed for {model_id}: {str(e)}")
            return 0

    def has_config_json(self, model_id):
        """Check if the repository has a config.json file"""
        try:
            files = self.api.list_repo_files(model_id)
            return "config.json" in files
        except Exception as e:
            print(f"Error checking config.json for {model_id}: {e}")
            return False

    def get_trending_models(self, limit=100):
        """Fetch trending models from Hugging Face API"""
        url = "https://huggingface.co/api/models"
        params = {"limit": limit}
        
        try:
            print(f"Making API request to: {url} with params: {params}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching models: {e}")
            return []

    def update_catalog(self, models):
        """Add new models to catalog if they don't exist"""
        current_catalog = self.load_catalog()
        
        for model in models:
            model_id = model['modelId']
            print(f"Processing model: {model_id}")
            
            if not self.has_config_json(model_id):
                print(f"Skipping {model_id} - config.json not found")
                continue
            
            if model_id not in current_catalog:
                parameters = model.get('config', {}).get('num_parameters')
                
                if parameters is None:
                    base_name = model_id.split('/')[-1]
                    parameters = get_model_size(base_name)
                
                if parameters is None or parameters == 0 or parameters == -1:
                    print(f"Estimating parameters via file size for {model_id}")
                    total_size = self.get_file_sizes(model_id)
                    if total_size > 0:
                        parameters = self.estimate_parameters(total_size)

                if parameters is None or parameters == 0:
                    print(f"Warning: {model_id} parameters could not be determined, setting to -1")
                    parameters = -1

                if parameters > self.MAX_PARAMETERS:
                    print(f"Skipping {model_id} - {parameters} parameters exceed limit.")
                    continue
                
                print(f"Adding {model_id} with parameters={parameters}")
                new_entry = {
                    "added": datetime.now().isoformat(),
                    "parameters": parameters,
                    "has_config": True,
                    "converted": False,
                    "attempts": 0,
                    "last_attempt": None,
                    "success_date": None,
                    "error_log": [],
                    "quantizations": []
                }
                
                if not self.model_catalog.add_model(model_id, new_entry):
                    print(f"Model {model_id} already exists in Redis")

    def cleanup_hf_cache(self, model_id):
        """Clean up Hugging Face cache folders for a specific model"""
        
        model_name = model_id.replace('/', '--')  # HF uses -- instead of / in cache paths
        cache_dir = Path(self.HF_CACHE_DIR)
        
        if not cache_dir.exists():
            print(f"No cache directory found at {cache_dir}")
            return
        
        deleted = False
        for entry in cache_dir.iterdir():
            if model_name in entry.name:
                try:
                    if entry.is_dir():
                        shutil.rmtree(entry)
                    else:
                        entry.unlink()
                    print(f"Deleted cache entry: {entry}")
                    deleted = True
                except Exception as e:
                    print(f"Failed to delete {entry}: {e}")
        
        if not deleted:
            print(f"No cache entries found for {model_id}")

    def convert_model(self, model_id):
        """Run conversion pipeline using the run_script function"""
        model_data = self.model_catalog.get_model(model_id)
        if not model_data:
            print(f"Model {model_id} not found in catalog")
            return

        model_data["attempts"] += 1
        model_data["last_attempt"] = datetime.now().isoformat()

        # First update the attempt count and last attempt time
        self.model_catalog.update_model_field(
            model_id,
            "attempts",
            model_data["attempts"]
        )
        self.model_catalog.update_model_field(
            model_id,
            "last_attempt",
            model_data["last_attempt"]
        )

        success = True
        try:
            print(f"Converting {model_id}...")
            scripts = [
                ("download_convert.py", [model_id]),
                ("make_files.py", [model_id]),
                ("upload-files.py", [model_id.split('/')[-1]])
            ]

            for script_name, script_args in scripts:
                print(f"Running {script_name}...")
                if not self.run_script(script_name, script_args):
                    print(f"Script {script_name} failed.")
                    success = False
                    break

        except Exception as e:
            model_data["error_log"].append(str(e))
            print(f"Conversion failed for {model_id}: {e}")
            success = False

        # Update converted status and success date if successful
        if success:
            print(f"Successfully converted {model_id}.")
            self.model_catalog.update_model_field(
                model_id,
                "converted",
                True
            )
            self.model_catalog.update_model_field(
                model_id,
                "success_date",
                datetime.now().isoformat()
            )
            # Clear error log on success
            self.model_catalog.update_model_field(
                model_id,
                "error_log",
                []
            )
        else:
            print(f"Conversion failed for {model_id}.")

        # Clean up cache if we've reached max attempts or succeeded
        if model_data["attempts"] >= self.MAX_ATTEMPTS or success:
            print(f"Max attempts reached or conversion succeeded for {model_id}, cleaning cache...")
            self.cleanup_hf_cache(model_id)

    def run_conversion_cycle(self):
        """Process all unconverted models in batch"""
        current_catalog = self.load_catalog()
        models = self.get_trending_models()
        self.update_catalog(models)

        try:
            for model_id, entry in current_catalog.items():
                parameters = entry.get("parameters", -1)

                if entry["converted"] or entry["attempts"] >= self.MAX_ATTEMPTS or parameters > self.MAX_PARAMETERS or parameters == -1:
                    print(f"Skipping {model_id} - converted={entry['converted']}, attempts={entry['attempts']}, parameters={parameters}")
                    continue

                if not entry["has_config"]:
                    print(f"Skipping {model_id} - config.json not found")
                    continue

                try:
                    self.convert_model(model_id)
                except Exception as e:
                    print(f"⚠ Error converting {model_id}: {e}")

        except Exception as e:
            print(f"Error during conversion cycle: {e}")

    def start_daemon(self):
        """Run continuously with 15 minute intervals"""
        while True:
            print("Starting conversion cycle...")
            self.run_conversion_cycle()
            print("Cycle complete. Sleeping for 15 minutes...")
            time.sleep(900)

            print("Updating and rebuilding llama.cpp...")
            if not build_and_copy():
                print("Warning: Failed to update or rebuild llama.cpp")

if __name__ == "__main__":
    converter = ModelConverter()
    converter.start_daemon()
