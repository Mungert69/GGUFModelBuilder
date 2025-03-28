import logging
import re
from huggingface_hub import HfApi

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO  # Logging level is set to INFO
)

def extract_parameter_size(model_id):
    """Extract the parameter size (in billions) from the model ID."""
    # Match patterns like "7b", "3b", "27b", etc.
    match = re.search(r"(\d+)(b|B)", model_id)
    if match:
        return int(match.group(1))  # Return the numeric part
    return None

def find_huggingface_model(model_name, max_parameters=15):
    """Search for the model on Hugging Face and return its ID and base model information."""
    api = HfApi()
    models = list(api.list_models(search=model_name))  # Fetch all models matching the search query
    if not models:
        return None

    # Filter models by parameter size
    filtered_models = []
    for model_info in models:
        try:
            # Extract the number of parameters from the model's config or name
            num_parameters = None

            # Check config for num_parameters
            if hasattr(model_info, "config") and model_info.config is not None:
                num_parameters = model_info.config.get("num_parameters", None)

            # If num_parameters is missing, infer from the model name
            if num_parameters is None:
                param_size = extract_parameter_size(model_info.modelId)
                if param_size is not None:
                    num_parameters = param_size * 1e9  # Convert to actual number

            # Filter by max_parameters
            if num_parameters is not None and num_parameters <= max_parameters * 1e9:
                filtered_models.append((model_info, num_parameters))
        except Exception as e:
            logging.warning(f"Error processing model {model_info.modelId}: {e}")

    if not filtered_models:
        logging.info(f"No models found with <= {max_parameters}B parameters.")
        return None

    # Sort filtered models by parameter size in descending order
    filtered_models.sort(key=lambda x: x[1], reverse=True)

    # Return the largest model smaller than the input value
    largest_model, num_parameters = filtered_models[0]
    base_model = None

    # Safely extract base_model from config if it exists
    if hasattr(largest_model, "config") and largest_model.config is not None:
        base_model = largest_model.config.get("base_model", None)

    return {
        "model_id": largest_model.modelId,
        "base_model": base_model,  # Extract base model if available
        "num_parameters": num_parameters  # Include the number of parameters
    }

def test_model_lookup():
    """Test function to look up a model on Hugging Face."""
    # Input model name
    model_name = input("Enter the model name to search on Hugging Face: ").strip()
    if not model_name:
        logging.error("No model name provided. Exiting.")
        return

    max_parameters = input("Enter the maximum parameter size (in billions, e.g., 7 for 7B): ").strip()
    max_parameters = int(max_parameters) if max_parameters.isdigit() else 15

    logging.info(f"Searching for model: {model_name} (max parameters: {max_parameters}B)")

    # Look up the model on Hugging Face
    model_info = find_huggingface_model(model_name, max_parameters=max_parameters)
    if model_info:
        logging.info(f"Model found on Hugging Face: {model_info['model_id']}")
        logging.info(f"Number of parameters: {model_info['num_parameters'] / 1e9}B")
        if model_info['base_model']:
            logging.info(f"Base model: {model_info['base_model']}")
        else:
            logging.info("No base model information available.")
    else:
        logging.info("Model not found on Hugging Face.")

if __name__ == "__main__":
    test_model_lookup()
