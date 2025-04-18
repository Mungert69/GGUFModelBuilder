import sys
import json
from datetime import datetime
from model_converter import ModelConverter

def process_model(converter, model_id):
    """Process a single model using the ModelConverter"""
    print(f"\nProcessing model: {model_id}")
    
    # Check if model exists in catalog and get its data
    model_data = converter.model_catalog.get_model(model_id)
    
    # If model doesn't exist in Redis, add it with default values
    if not model_data:
        print(f"Adding new model to catalog: {model_id}")
        model_data = {
            "added": datetime.now().isoformat(),
            "parameters": 0,  # Will be updated during conversion
            "has_config": True,  # Assuming it has config since we're converting it
            "converted": False,
            "attempts": 0,
            "last_attempt": None,
            "success_date": None,
            "error_log": [],
            "quantizations": []
        }
        if not converter.model_catalog.add_model(model_id, model_data):
            print(f"Failed to add model {model_id} to catalog")

    # Run the conversion using the existing convert_model method
    converter.convert_model(model_id)

def main():
    if len(sys.argv) != 2:
        print("Usage: python run_all_from_json.py <path_to_models_json>")
        sys.exit(1)

    # Initialize the converter with Redis connection
    converter = ModelConverter()
    
    # Load model list from JSON
    try:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
            model_ids = data.get("models", [])
            if isinstance(model_ids, dict):  # Handle case where models is an object
                model_ids = list(model_ids.keys())
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        sys.exit(1)

    if not model_ids:
        print("No model IDs found in the JSON file.")
        sys.exit(1)

    print(f"Found {len(model_ids)} models to process")
    
    # Process each model
    for i, model_id in enumerate(model_ids, 1):
        print(f"\nProcessing model {i}/{len(model_ids)}")
        process_model(converter, model_id)

    print("\nAll models processed.")

if __name__ == "__main__":
    main()
