import os
import json
import time
import requests
from datetime import datetime
from run_all_from_json import run_script  # Import the run_script function
from dotenv import load_dotenv
from make_files import get_model_size  # Import get_model_size from make_files.py
from huggingface_hub import HfApi, HfFileSystem, login  # Import for authentication
from build_llama import build_and_copy

load_dotenv()  # Load environment variables

class ModelConverter:
    def __init__(self):
        self.catalog_file = "model_catalog.json"
        self.catalog = self.load_catalog()
        self.hf_token = os.getenv("HF_API_TOKEN")
        self.MAX_PARAMETERS = 9e9  # 9 billion parameters
        
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
        
        self.api = HfApi()  # Initialize API client
        self.fs = HfFileSystem()  # Initialize File System client
    

    def estimate_parameters(self, file_size):
        """Estimate the number of parameters based on file size."""
        if file_size == 0:
            return 0  # Ensure zero instead of None

        # Handling both float32 (4 bytes) and bfloat16/float16 (2 bytes)
        estimated_params_fp32 = file_size / 4
        estimated_params_fp16 = file_size / 2  # If model uses bfloat16 or float16

        print(f"Estimated parameters (FP32): {estimated_params_fp32}, (FP16/BF16): {estimated_params_fp16}")

        # Use FP32 estimation by default, but FP16/BF16 if model is known to use it
        return estimated_params_fp32  

    def load_catalog(self):
        try:
            with open(self.catalog_file, "r") as f:
                catalog = json.load(f)
                
                # Ensure has_config field exists
                for model_id, entry in catalog.items():
                    if "has_config" not in entry:
                        entry["has_config"] = self.has_config_json(model_id)
                        
                return catalog
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
           
    def get_file_sizes(self, model_id):
        """Get the total size of .safetensors files in the repository as a fallback for parameter estimation."""
        try:
            print(f"\n[DEBUG] Starting file size check for: {model_id}")
            
            # Ensure the repository exists and is accessible
            try:
                repo_info = self.api.repo_info(model_id, repo_type="model")
                print(f"[DEBUG] Repository found: {repo_info.id}")
            except Exception as repo_err:
                print(f"[ERROR] Repository not found or inaccessible: {model_id}")
                print(f"[ERROR] Details: {str(repo_err)}")
                return 0

            # Use HfFileSystem to list and sum sizes of .safetensors files
            try:
                # Try both `models` and `datasets` namespaces
                paths_to_check = [
                    f"models/{model_id}",  # Standard models path
                    f"datasets/{model_id}",  # Some models are under datasets
                    f"{model_id}",  # Try without any namespace
                ]

                total_size = 0
                found_files = False

                for path in paths_to_check:
                    print(f"[DEBUG] Checking path: {path}")
                    
                    try:
                        # List files in the repository
                        files = self.fs.ls(path, detail=True)
                        print(f"[DEBUG] Found {len(files)} files in {path}:")
                        for f in files:
                            print(f" - {f['name']} ({f['size']} bytes)")
                        
                        # Filter for .safetensors files
                        safetensors_files = [f for f in files if f['name'].endswith('.safetensors')]
                        if safetensors_files:
                            found_files = True
                            total_size += sum(f['size'] for f in safetensors_files)
                    except Exception as ls_err:
                        print(f"[DEBUG] Failed to list files in {path}: {str(ls_err)}")

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

    def save_catalog(self):
        """
        Save the catalog to a file, merging in data from an external file (models_catalog_new.json).
        Uses atomic write to avoid corruption.
        """
        external_file = "model_catalog_new.json"
        temp_file = self.catalog_file + ".tmp"

        # Step 1: Load data from the external file (if it exists)
        if os.path.exists(external_file):
            try:
                with open(external_file, "r") as f:
                    external_catalog = json.load(f)
                    print(f"Loaded external catalog from {external_file}")

                # Step 2: Merge external data into the main catalog
                for model_id, external_entry in external_catalog.items():
                    if model_id not in self.catalog:
                        # Add new entry
                        self.catalog[model_id] = external_entry
                        print(f"Added new model from external catalog: {model_id}")

            except Exception as e:
                print(f"⚠ Error loading or merging external catalog: {e}")
            finally:
                # Step 3: Clean up the external file after merging
                try:
                    os.remove(external_file)
                    print(f"Deleted external catalog file: {external_file}")
                except Exception as e:
                    print(f"⚠ Error deleting external catalog file: {e}")

        # Step 4: Save the merged catalog atomically
        try:
            with open(temp_file, "w") as f:
                json.dump(self.catalog, f, indent=2)
            os.replace(temp_file, self.catalog_file)
            print(f"Saved merged catalog to {self.catalog_file}")
        except Exception as e:
            print(f"⚠ Error saving catalog: {e}")

    def get_trending_models(self, limit=100):
        """Fetch trending models from Hugging Face API"""
        url = "https://huggingface.co/api/models"
        params = {"limit": limit}
        
        try:
            print(f"Making API request to: {url} with params: {params}")  # Debug logging
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching models: {e}")
            return []

    def has_config_json(self, model_id):
        """Check if the repository has a config.json file"""
        try:
            files = self.api.list_repo_files(model_id)
            return "config.json" in files
        except Exception as e:
            print(f"Error checking config.json for {model_id}: {e}")
            return False
    def update_catalog(self, models):
        """Add new models to catalog if they don't exist"""
        for model in models:
            model_id = model['modelId']
            print(f"Processing model: {model_id}")  # Debugging log
            
            if not self.has_config_json(model_id):
                print(f"Skipping {model_id} - config.json not found")
                continue
            
            if model_id not in self.catalog:
                parameters = model.get('config', {}).get('num_parameters')
            # Check if parameters were already set in a previous loop
                if parameters is None and model_id in self.catalog:
                    parameters = self.catalog[model_id].get("parameters", -1)
                if parameters is None:
                    base_name = model_id.split('/')[-1]
                    parameters = get_model_size(base_name)  # From make_files.py
                
                if parameters is None or parameters == 0 or parameters == -1 :
                    print(f"Estimating parameters via file size for {model_id}")
                    total_size = self.get_file_sizes(model_id)
                    if total_size > 0:
                        parameters = self.estimate_parameters(total_size)

                if parameters is None or parameters == 0:
                    print(f"Warning: {model_id} parameters could not be determined, setting to -1 as a flag.")
                    parameters = -1  # Set to -1 to flag that parameter estimation failed.

                if parameters > self.MAX_PARAMETERS:
                    print(f"Skipping {model_id} - {parameters} parameters exceed limit.")
                    continue
                
                print(f"Adding {model_id} with parameters={parameters}")
                self.catalog[model_id] = {
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
        

    def convert_model(self, model_id):
        """Run conversion pipeline using the run_script function"""
        entry = self.catalog[model_id]
        entry["attempts"] += 1
        entry["last_attempt"] = datetime.now().isoformat()

        success = True  # Assume success initially

        try:
            print(f"Converting {model_id}...")

            # Run each script and check for success
            scripts = [
                ("download_convert.py", [model_id, model_id.split('/')[-1]]),
                ("make_files.py", [model_id]),
                ("upload-files.py", [model_id.split('/')[-1]])
            ]

            for script_name, script_args in scripts:
                print(f"Running {script_name}...")
                if not run_script(script_name, script_args):
                    print(f"Script {script_name} failed.")
                    success = False
                    break  # Stop further execution if any script fails

            if success:
                # Only mark as converted if all scripts succeeded
                entry["converted"] = True
                entry["success_date"] = datetime.now().isoformat()
                entry["error_log"] = []
                print(f"Successfully converted {model_id}.")
            else:
                print(f"Conversion failed for {model_id} due to script errors.")

        except Exception as e:
            entry["error_log"].append(str(e))
            print(f"Conversion failed for {model_id}: {e}")

    def run_conversion_cycle(self):
        """Process all unconverted models in batch (read once, write once)."""

        # 🔹 Read the catalog at the start of the loop
        self.catalog = self.load_catalog()  # Load only once per cycle

        # 🔹 Fetch and update the model list
        models = self.get_trending_models()
        self.update_catalog(models)

        try:
            for model_id, entry in self.catalog.items():
                parameters = entry.get("parameters", -1)  # Default to -1 if missing

                # Ensure parameters are properly updated
                if parameters is None:
                    parameters = -1  # Prevent None from causing issues

                print(f"Checking model {model_id} with parameters={parameters}")

                # Skip models that are already converted or exceed limits
                if entry["converted"] or entry["attempts"] >= 3 or parameters > self.MAX_PARAMETERS or parameters == -1:
                    print(f"Skipping {model_id} - converted={entry['converted']}, attempts={entry['attempts']}, parameters={parameters}")
                    continue

                if not entry["has_config"]:
                    print(f"Skipping {model_id} - config.json not found")
                    continue

                # 🔹 Run conversion but DO NOT save catalog inside convert_model
                try:
                    self.convert_model(model_id)
                except Exception as e:
                    entry["error_log"].append(f"Error during conversion: {str(e)}")
                    print(f"⚠️ Error converting {model_id}: {e}")

        finally:
            # 🔹 Ensure we always save the catalog, even if errors occur
            print("Saving updated catalog after processing all models...")
            self.save_catalog()

    def start_daemon(self):  # Properly indented to be part of the ModelConverter class
        """Run continuously with 15 minute intervals"""
        while True:
            print("Starting conversion cycle...")
            self.run_conversion_cycle()
            print("Cycle complete. Sleeping for 15 minutes...")
            time.sleep(900)  # 15 minutes

            # Call build_and_copy after each sleep
            print("Updating and rebuilding llama.cpp...")
            if not build_and_copy():
                print("Warning: Failed to update or rebuild llama.cpp")


if __name__ == "__main__":
    converter = ModelConverter()
    converter.start_daemon()

