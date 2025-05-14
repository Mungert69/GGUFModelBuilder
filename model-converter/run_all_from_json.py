import sys
import json
from datetime import datetime
from model_converter import ModelConverter

def process_model(converter, model_entry):
    """Processes a single model entry by ensuring its presence in the catalog and running the conversion.

    This function adds the model to the catalog if it does not exist, updates its MoE status if needed, and initiates the model conversion process.

    Args:
        converter: The ModelConverter instance used for catalog operations and conversion.
        model_entry: The model entry, either as a string (model name) or a dictionary with model details.

    Returns:
        None

    Raises:
        RuntimeError: If adding the model to the catalog or updating its MoE status fails.
    """

    if isinstance(model_entry, str):
        model_id = model_entry
        is_moe = False  # Default for backward compatibility
    else:
        model_id = model_entry["name"]
        is_moe = model_entry.get("is_moe", False)
    
    print(f"\nProcessing model: {model_id} (MoE: {'Yes' if is_moe else 'No'})")
    
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
            "quantizations": [],
            "is_moe": is_moe
        }
        if not converter.model_catalog.add_model(model_id, model_data):
            print(f"Failed to add model {model_id} to catalog")
            raise RuntimeError(f"Failed to add model {model_id} to Redis catalog")

    # Update MoE status if it's different from what's in Redis
    if model_data.get("is_moe", False) != is_moe:
        print(f"Updating MoE status for {model_id} to {is_moe}")
        if not converter.model_catalog.update_model_field(
            model_id,
            "is_moe",
            is_moe
        ):
            raise RuntimeError(f"Failed to update MoE status for {model_id}")

    # Run the conversion - will raise exception on failure
    converter.convert_model(model_id, is_moe)

def main():
    """Runs the batch model conversion process using a JSON file as input.

    This function loads a list of models from a JSON file, initializes the converter, and processes each model entry in sequence.

    Returns:
        None

    Raises:
        SystemExit: If the input arguments are invalid or if any error occurs during processing.
    """
    if len(sys.argv) != 2:
        print("Usage: python run_all_from_json.py <path_to_models_json>")
        sys.exit(1)

    # Initialize the converter with Redis connection
    converter = ModelConverter()
    
    # Load model list from JSON
    try:
        with open(sys.argv[1], "r") as f:
            data = json.load(f)
            model_entries = data.get("models", [])
            
            if not model_entries:
                print("No models found in the JSON file.")
                sys.exit(1)
                
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        sys.exit(1)

    print(f"Found {len(model_entries)} models to process")
    
    # Process each model - will stop on first failure
    try:
        for i, model_entry in enumerate(model_entries, 1):
            print(f"\nProcessing model {i}/{len(model_entries)}")
            process_model(converter, model_entry)
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        print("Stopping processing due to failure.")
        sys.exit(1)

    print("\nAll models processed successfully.")

if __name__ == "__main__":
    main()
