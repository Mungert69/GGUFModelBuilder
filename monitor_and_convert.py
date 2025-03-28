import os
import json
import time
import requests
from datetime import datetime
import subprocess
from dotenv import load_dotenv

load_dotenv()  # Load environment variables

class ModelConverter:
    def __init__(self):
        self.catalog_file = "model_catalog.json"
        self.catalog = self.load_catalog()
        self.hf_token = os.getenv("HF_API_TOKEN")
        
    def load_catalog(self):
        try:
            with open(self.catalog_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
            
    def save_catalog(self):
        with open(self.catalog_file, "w") as f:
            json.dump(self.catalog, f, indent=2)

    def get_trending_models(self, limit=50):
        """Fetch trending models from Hugging Face API"""
        url = "https://huggingface.co/api/models"
        params = {
            "sort": "trending",
            "limit": limit,
            "full": True
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching models: {e}")
            return []

    def update_catalog(self, models):
        """Add new models to catalog if they don't exist"""
        for model in models:
            model_id = model['modelId']
            if model_id not in self.catalog:
                self.catalog[model_id] = {
                    "added": datetime.now().isoformat(),
                    "parameters": model.get('config', {}).get('num_parameters'),
                    "converted": False,
                    "attempts": 0,
                    "last_attempt": None,
                    "success_date": None,
                    "error_log": [],
                    "quantizations": []
                }
        self.save_catalog()

    def convert_model(self, model_id):
        """Run conversion pipeline with error handling"""
        entry = self.catalog[model_id]
        entry["attempts"] += 1
        entry["last_attempt"] = datetime.now().isoformat()
        self.save_catalog()

        try:
            # Step 1: Download and convert to GGUF
            print(f"Converting {model_id}...")
            download_result = subprocess.run(
                ["python3", "download_convert.py", model_id, "./temp"],
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes
            )
            
            if download_result.returncode != 0:
                raise RuntimeError(f"Download failed: {download_result.stderr}")

            # Step 2: Quantization
            quant_result = subprocess.run(
                ["python3", "make_files.py", model_id],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour
            )
            
            if quant_result.returncode != 0:
                raise RuntimeError(f"Quantization failed: {quant_result.stderr}")

            # Step 3: Upload
            upload_result = subprocess.run(
                ["python3", "upload-files.py", model_id],
                capture_output=True,
                text=True,
                timeout=1200  # 20 minutes
            )

            if upload_result.returncode == 0:
                entry["converted"] = True
                entry["success_date"] = datetime.now().isoformat()
                entry["error_log"] = []
            else:
                raise RuntimeError(f"Upload failed: {upload_result.stderr}")

        except Exception as e:
            entry["error_log"].append(str(e))
            print(f"Conversion failed for {model_id}: {e}")
            
        finally:
            self.save_catalog()

    def run_conversion_cycle(self):
        """Process all unconverted models"""
        models = self.get_trending_models()
        self.update_catalog(models)

        for model_id in self.catalog:
            entry = self.catalog[model_id]
            
            if entry["converted"]:
                continue
                
            if entry["attempts"] >= 3:
                print(f"Skipping {model_id} - too many attempts")
                continue
                
            self.convert_model(model_id)
            time.sleep(60)  # Rate limit between conversions

    def start_daemon(self):
        """Run continuously with 15 minute intervals"""
        while True:
            print("Starting conversion cycle...")
            self.run_conversion_cycle()
            print("Cycle complete. Sleeping for 15 minutes...")
            time.sleep(900)  # 15 minutes

if __name__ == "__main__":
    converter = ModelConverter()
    converter.start_daemon()
