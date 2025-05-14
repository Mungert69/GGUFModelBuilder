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
        # Minimum disk space required for conversion (in GB)
        self.MIN_DISK_SPACE_GB = 10

        # Initialize Redis connection
        REDIS_HOST = os.getenv("REDIS_HOST", "redis.readyforquantum.com")
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
        self.MAX_PARAMETERS = 33e9  # max < 33 billion parameters
        self.MAX_ATTEMPTS = 3        
        self.HF_CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")
        self.SAFETY_FACTOR = 1.1  # 10% extra space buffer
        self.BYTES_PER_PARAM = 2  # BF16 uses 2 bytes per parameter

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
        self.EXCLUDED_COMPANIES = [
            "VIDraft",  
            "openfree",
            "agentica-org"
        ]
    
    def calculate_required_space(self, model_id):
        """Calculate required disk space in GB for conversion"""
        model_data = self.model_catalog.get_model(model_id)
        if not model_data:
            return 0
        
        params = model_data.get("parameters", 0)
        if params <= 0:
            return 0
        
        # Calculate space for 3 copies (original BF16 + working copy + split files)
        bytes_needed = params * self.BYTES_PER_PARAM * 3
        gb_needed = (bytes_needed / (1024**3)) * self.SAFETY_FACTOR
        return max(gb_needed, self.MIN_DISK_SPACE_GB)
    
    def can_fit_model(self, model_id):
        """Check if we have space for this model + buffer"""
        required_gb = self.calculate_required_space(model_id)
        if required_gb == 0:
            print(f"⚠️ Couldn't determine size for {model_id}")
            return False
        
        disk_free = self.get_disk_usage()['free_gb']
        can_fit = disk_free >= required_gb
        
        print(f"📊 Space check for {model_id}: "
            f"Need {required_gb:.1f}GB, have {disk_free:.1f}GB "
            f"({'✅' if can_fit else '❌'})")
        
        return can_fit
    def get_disk_usage(self, path="."):
        """Return disk usage statistics in GB"""
        usage = shutil.disk_usage(path)
        return {
            'total_gb': usage.total / (1024**3),
            'used_gb': usage.used / (1024**3),
            'free_gb': usage.free / (1024**3),
            'path': os.path.abspath(path)
        }
    
    def check_disk_space(self, required_gb=10):
        """Check if we have enough disk space"""
        usage = self.get_disk_usage()
        if usage['free_gb'] < max(required_gb, self.MIN_DISK_SPACE_GB):
            print(f"⚠️ Low disk space: {usage['free_gb']:.2f}GB free in {usage['path']}")
            return False
        return True
    
    def get_largest_cache_items(self, path, limit=5):
        """Return the largest items in a directory"""
        try:
            items = []
            for item in Path(path).glob('*'):
                try:
                    size = sum(f.stat().st_size for f in item.glob('**/*') if f.is_file())
                    items.append((item.name, size / (1024**3)))  # Size in GB
                except:
                    continue
            return sorted(items, key=lambda x: x[1], reverse=True)[:limit]
        except Exception as e:
            print(f"Error scanning cache: {e}")
            return []
    def is_excluded_company(self, model_id):
        """Check if the model belongs to an excluded company"""
        company = model_id.split('/')[0]
        return company in self.EXCLUDED_COMPANIES

    def run_script(self, script_name, args):
        """Runs a script with arguments and streams output in real time.
        Returns True if the script succeeds, False otherwise."""
        script_path = os.path.join(os.getcwd(), script_name)
        if not os.path.exists(script_path):
            print(f"Error: Script {script_name} not found at {script_path}")
            return False

        print(f"\nRunning {script_name} with arguments: {args}")

        # Collect all output for error reporting
        output_lines = []
        error_lines = []

        process = subprocess.Popen(
            ["python3", script_path] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,  # Line buffering
            universal_newlines=True  # Read as text
        )

        # Read output in real time while also collecting it
        def read_output(pipe, collection, is_stderr=False):
            for line in iter(pipe.readline, ''):
                collection.append(line)
                if is_stderr:
                    sys.stderr.write(line)
                else:
                    sys.stdout.write(line)
                sys.stdout.flush()
            pipe.close()

        stdout_thread = threading.Thread(
            target=read_output,
            args=(process.stdout, output_lines)
        )
        stderr_thread = threading.Thread(
            target=read_output,
            args=(process.stderr, error_lines, True)
        )
        
        stdout_thread.start()
        stderr_thread.start()

        process.wait()
        stdout_thread.join()
        stderr_thread.join()

        exit_code = process.returncode
        if exit_code != 0:
            print(f"\nError running {script_name}, exited with code {exit_code}")
            print("Error output:")
            print(''.join(error_lines))
            return False
        return True

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

    def check_moe_from_readme(self, model_id):
        """Check if a model is MoE by parsing its README file"""
        try:
            # Try to get README content from Hugging Face
            readme_url = f"https://huggingface.co/{model_id}/raw/main/README.md"
            response = requests.get(readme_url)
            response.raise_for_status()
            readme_content = response.text.lower()  # Case insensitive search

            # Common MoE indicators in READMEs
            moe_keywords = [
                'mixture of experts',
                'moe',
                'multiple experts'
            ]

            # Check for any MoE indicators
            is_moe = any(keyword in readme_content for keyword in moe_keywords)
            print(f"MoE check for {model_id}: {'Yes' if is_moe else 'No'}")
            return is_moe

        except requests.exceptions.RequestException as e:
            print(f"Couldn't fetch README for {model_id}: {e}")
            return False
        except Exception as e:
            print(f"Error parsing README for {model_id}: {e}")
            return False
    def check_moe_from_config(self, model_id):
        """Check if model is MoE by examining field names in its config.json"""
        try:
            config_url = f"https://huggingface.co/{model_id}/raw/main/config.json"
            response = requests.get(config_url)
            response.raise_for_status()
            config = response.json()
            
            # Convert all keys to lowercase for case-insensitive search
            all_keys = [k.lower() for k in config.keys()]
            
            # Check if any key contains 'moe'
            moe_keys = [k for k in all_keys if 'moe' in k]
            
            if moe_keys:
                print(f"Found MoE indicators in config for {model_id}: {moe_keys}")
                return True
                
            # Also check nested dictionaries recursively
            def check_nested(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if 'moe' in str(key).lower():
                            return True
                        if check_nested(value):
                            return True
                elif isinstance(obj, (list, tuple)):
                    for item in obj:
                        if check_nested(item):
                            return True
                return False
            
            if check_nested(config):
                print(f"Found nested MoE indicators in config for {model_id}")
                return True
                
            return False
            
        except Exception as e:
            print(f"Error checking config for {model_id}: {e}")
            return False

    def is_moe_model(self, model_id):
        """Main MoE detection method that tries multiple approaches"""
        try:
            # First try config.json (most reliable)
            if self.check_moe_from_config(model_id):
                return True
                

            return False
        except Exception as e:
            print(f"MoE detection failed for {model_id}: {e}")
            return False

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
                is_moe = self.check_moe_from_config(model_id)
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
                    "quantizations": [],
                    "is_moe": is_moe
                }
                
                if not self.model_catalog.add_model(model_id, new_entry):
                    print(f"Model {model_id} already exists in Redis")

    def aggressive_cache_cleanup(self):
        """Force clean all possible cache locations"""
        print("⚡ Performing aggressive cache cleanup")
        
        # 1. Clear Hugging Face cache
        self.cleanup_hf_cache("*")  # Special case for all caches
        
        # 2. Clear model working directories
        model_dirs = [d for d in Path(self.MODEL_WORK_DIR).glob("*") if d.is_dir()]
        for dir in model_dirs:
            try:
                shutil.rmtree(dir)
                print(f"Deleted working directory: {dir}")
            except Exception as e:
                print(f"Failed to delete {dir}: {e}")
        
        # 3. Clear any temporary files
        temp_files = list(Path(".").glob("*.tmp")) + list(Path(".").glob("*.temp"))
        for file in temp_files:
            try:
                file.unlink()
            except:
                pass

    def cleanup_hf_cache(self, model_id="*"):
        """Enhanced cache cleanup with disk space check"""
        if model_id == "*":
            # Clean entire cache directory
            cache_path = self.HF_CACHE_DIR
            print(f"🧹 Cleaning entire HF cache at {cache_path}")
            try:
                shutil.rmtree(cache_path)
                os.makedirs(cache_path, exist_ok=True)
                print("✅ Entire HF cache cleared")
            except Exception as e:
                print(f"❌ Failed to clear HF cache: {e}")
        else:
            # Original single-model cleanup
            model_name = model_id.replace('/', '--')
            cache_path = os.path.join(self.HF_CACHE_DIR, f"models--{model_name}")
            if os.path.exists(cache_path):
                try:
                    shutil.rmtree(cache_path)
                    print(f"✅ Cleared HF cache for {model_id}")
                except Exception as e:
                    print(f"❌ Failed to clear cache for {model_id}: {e}")

    def convert_model(self, model_id, is_moe):
        """Run conversion pipeline using the run_script function"""
        model_data = self.model_catalog.get_model(model_id)
        if not model_data:
            print(f"Model {model_id} not found in catalog")
            return
        required_gb = self.calculate_required_space(model_id)
        if not required_gb:
            print(f"❌ Cannot determine space requirements for {model_id}")
            return
        
        # Check space with model-specific requirements
        if not self.can_fit_model(model_id):
            print(f"🚨 Insufficient space for {model_id} (needs {required_gb:.1f}GB)")
            
            # Try targeted cleanup first
            self.cleanup_completed_models()
            if not self.can_fit_model(model_id):
                # Emergency measures if still not enough space
                print("⚡ Attempting targeted large file cleanup...")
                self.remove_largest_cache_items()
                if not self.can_fit_model(model_id):
                    print("❌ Critical: Still insufficient space after cleanup")
                    return
        
        model_data["attempts"] = int(model_data.get("attempts", 0)) + 1
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
                ("make_files.py", [model_id, "--is_moe"] if is_moe else [model_id]),
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
                is_moe = entry.get("is_moe", False)
                if self.is_excluded_company(model_id):
                    print(f"Skipping {model_id} - from excluded company")
                    continue
                parameters = entry.get("parameters", -1)

                if entry["converted"] or entry["attempts"] >= self.MAX_ATTEMPTS or parameters > self.MAX_PARAMETERS or parameters == -1:
                    print(f"Skipping {model_id} - converted={entry['converted']}, attempts={entry['attempts']}, parameters={parameters}")
                    continue

                if not entry["has_config"]:
                    print(f"Skipping {model_id} - config.json not found")
                    continue
                is_moe = entry.get("is_moe", False) 
                try:
                    self.convert_model(model_id, is_moe)
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
