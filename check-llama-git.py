import os
import json
import logging
import requests
import re
from datetime import datetime
from llama_cpp import Llama, LlamaGrammar
from huggingface_hub import HfApi
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Read the API token from the .env file
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO  # Logging level is set to INFO
)

# GitHub API settings
GITHUB_REPO = "ggml-org/llama.cpp"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
LAST_COMMIT_FILE = "last_commit.txt"
COMMITS_CACHE_FILE = "commits_cache.json"  # File to cache fetched commits
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
MAX_TOKENS = 2048

# Local GGUF model
LOCAL_MODEL_PATH = "./Qwen2.5-1.5B-Instruct-q8_0.gguf"
GRAMMAR_FILE_PATH = "./llama.cpp/grammars/json.gbnf"  # Path to your JSON grammar file

# Load quantized GGUF model using llama-cpp-python
logging.info("Loading quantized GGUF model...")
try:
    llm = Llama(
        model_path=LOCAL_MODEL_PATH,  # Path to the model
        n_ctx=MAX_TOKENS,  # Set the context window size to 8048 tokens
        verbose=False  # Disable verbose logging for cleaner output
    )
    logging.info("Model loaded successfully with a context window of 8048 tokens.")
except Exception as e:
    logging.error(f"Failed to load model: {e}")
    exit(1)

# Load the JSON grammar
logging.info("Loading JSON grammar...")
try:
    with open(GRAMMAR_FILE_PATH, 'r') as file:
        grammar_content = file.read()
    grammar = LlamaGrammar.from_string(grammar_content)
    logging.info("Grammar loaded successfully.")
except Exception as e:
    logging.error(f"Failed to load grammar: {e}")
    exit(1)

def fetch_last_50_commits():
    """Fetch the last 50 commits from GitHub API and cache them."""
    logging.info(f"Fetching last 50 commits from {GITHUB_REPO}...")
    try:
        params = {"per_page": 50}  # Fetch up to 50 commits
        response = requests.get(GITHUB_API_URL, headers=HEADERS, params=params, timeout=10)
        response.raise_for_status()
        commits = response.json()
        if not commits:
            logging.warning("No commits found!")
            return None

        logging.info(f"Fetched {len(commits)} commits from GitHub API.")

        # Cache the commits to a file
        with open(COMMITS_CACHE_FILE, "w") as f:
            json.dump(commits, f, indent=2)
        logging.info(f"Commits cached to {COMMITS_CACHE_FILE}.")

        return commits

    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return None

def load_cached_commits():
    """Load commits from the cache file if it exists."""
    if os.path.exists(COMMITS_CACHE_FILE):
        logging.info(f"Loading cached commits from {COMMITS_CACHE_FILE}...")
        with open(COMMITS_CACHE_FILE, "r") as f:
            return json.load(f)
    logging.info("No cached commits found.")
    return None

def fetch_commit_details(commit_sha):
    """Fetch details for a specific commit, including file changes and diffs."""
    logging.info(f"Fetching details for commit {commit_sha}...")
    try:
        commit_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{commit_sha}"
        commit_response = requests.get(commit_url, headers=HEADERS, timeout=10)
        commit_response.raise_for_status()
        return commit_response.json()
    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return None

def analyze_commit(commit):
    """Analyze commit message, file names, and diffs to detect new models using the LLM."""
    commit_sha = commit.get("sha", "UNKNOWN_SHA")
    message = commit.get("commit", {}).get("message", "No commit message found")
    files = commit.get("files", [])  # List of files changed in the commit

    logging.info(f"Analyzing commit {commit_sha}...")
    logging.info(f"Commit message: {message}")

    # Log all files in the commit for debugging
    all_files = [file.get("filename", "") for file in files]
    logging.info(f"All files in commit: {json.dumps(all_files, indent=2)}")
    # Extract file names and diffs, but only for relevant files
    file_changes = []
    for file in files:
        filename = file.get("filename", "")
        patch = file.get("patch", "")  # Unified diff for the file

        # Check if the file is relevant to model addition
        if (
            any(keyword in filename.lower() for keyword in ["convert", "hf_to_gguf", "models"])  # Keywords
            or filename.startswith("scripts/")  # Scripts directory
        ):
            file_changes.append({"filename": filename, "patch": patch})

    logging.info(f"Relevant file changes: {json.dumps(file_changes, indent=2)}")

    # Base prompt template
    base_prompt = (
        "You are an AI assistant. Analyze the following information to determine if a new AI model is being added.\n"
        "Respond ONLY in valid JSON format. Your response must be a complete JSON object with no extra text.\n"
        "The response should look like this:\n"
        "{{\n"
        '  "is_new_model": true/false,\n'
        '  "model_name_if_found": "Name of the model if detected, otherwise null",\n'
        '  "reason_for_answer": "Explain why or why not."\n'
        "}}\n"
        "Return only the JSON structure, without any extra words, explanations, or formatting.\n"
    )

    # Helper message to remind the LLM of its task
    helper_message = (
        "\n\nRemember: Your task is to analyze the commit message and file changes (if any) to determine if a new AI model is being added. "
        "Look at the commit message and file changes to make your decision."
    )

    # Add file changes context if available
    if file_changes:
        file_context = "File changes:\n" + "\n".join([f["filename"] for f in file_changes])
    else:
        file_context = "No relevant file changes were found."

    # Build the final prompt
    prompt = base_prompt + file_context + "\n\nCommit message:\n" + message + helper_message

    # Calculate token limits
    prompt_tokens = len(prompt.split())  # Rough token count (1 token ≈ 1 word)

    # Truncate the prompt if it exceeds the token limit (prioritize the commit message)
    if prompt_tokens > MAX_TOKENS:
        # Truncate file changes to fit within the token limit
        available_tokens = MAX_TOKENS - len(base_prompt.split()) - len(helper_message.split()) - len(message.split())
        truncated_file_changes = file_changes[:available_tokens]
        file_context = "File changes (truncated):\n" + "\n".join([f["filename"] for f in truncated_file_changes])
        prompt = base_prompt + file_context + "\n\nCommit message:\n" + message + helper_message

    try:
        llm_response = llm(
            prompt,
            max_tokens=MAX_TOKENS,  # Adjust token size if needed
            stop=None,  # Avoid prematurely stopping
            echo=False,
            grammar=grammar  # Apply the grammar during inference
        )

        # Log the raw LLM response
        response_text = llm_response.get("choices", [{}])[0].get("text", "").strip()
        logging.info(f"Raw LLM Response: {response_text}")

        # Clean the response to ensure it's valid JSON
        response_text = response_text.strip()
        if not response_text.startswith("{") or not response_text.endswith("}"):
            # Attempt to extract JSON from the response
            start_idx = response_text.find("{")
            end_idx = response_text.rfind("}") + 1
            if start_idx == -1 or end_idx == -1:
                raise ValueError("No valid JSON found in LLM response.")
            response_text = response_text[start_idx:end_idx]

        # Parse the JSON response
        llm_output = json.loads(response_text)

        # Validate the JSON structure
        if not all(key in llm_output for key in ["is_new_model", "model_name_if_found", "reason_for_answer"]):
            raise ValueError("LLM response is missing required fields.")

        is_new_model = llm_output.get("is_new_model", False)
        model_name = llm_output.get("model_name_if_found", None)
        reason = llm_output.get("reason_for_answer", "No reason provided.")

        logging.info(f"LLM Decision: {is_new_model}")
        logging.info(f"LLM Reason: {reason}")
        if model_name:
            logging.info(f"LLM Detected Model Name: {model_name}")

        return is_new_model, model_name

    except (json.JSONDecodeError, ValueError) as e:
        logging.error(f"Invalid LLM response format: {e}")
        logging.error(f"Raw LLM Response (before failure): {response_text}")
        return False, None

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

def main():
    """Main monitoring function."""
    last_commit = None
    if os.path.exists(LAST_COMMIT_FILE):
        with open(LAST_COMMIT_FILE, "r") as f:
            last_commit = f.read().strip()
        logging.info(f"Last processed commit SHA: {last_commit}")
    else:
        logging.info("No last processed commit found. Starting from the latest commit.")

    # Load cached commits or fetch new ones
    commits = load_cached_commits()
    if not commits:
        commits = fetch_last_50_commits()
        if not commits:
            logging.info("No commits found.")
            return

    logging.info(f"Processing {len(commits)} commits...")

    # Process each commit
    for commit in commits:
        commit_sha = commit.get("sha", "UNKNOWN_SHA")
        logging.info(f"Processing commit: {commit_sha}")

        # Skip if this commit has already been processed
        if commit_sha == last_commit:
            logging.info(f"Reached previously processed commit: {commit_sha}. Stopping further checks.")
            break

        logging.info(f"Checking commit {commit_sha}...")

        # Fetch commit details if not already available
        if "files" not in commit:
            commit = fetch_commit_details(commit_sha)
            if not commit:
                continue

        # Analyze the commit
        is_new_model, model_name = analyze_commit(commit)
        if is_new_model and model_name:
            logging.info(f"New model detected: {model_name}")
            
            # Look up the base model on Hugging Face
            model_info = find_huggingface_model(model_name, max_parameters=15)  # Set max_parameters as needed
            if model_info:
                logging.info(f"Model found on Hugging Face: {model_info['model_id']}")
                logging.info(f"Number of parameters: {model_info['num_parameters'] / 1e9}B")
                if model_info['base_model']:
                    logging.info(f"Base model: {model_info['base_model']}")
                else:
                    logging.info("No base model information available.")
            else:
                logging.info("Model not found on Hugging Face.")

            # Handle the new model (e.g., download and convert)
            with open(LAST_COMMIT_FILE, "w") as f:
                f.write(commit_sha)
            break  # Stop after processing the first new model
        else:
            logging.info("No model-related changes detected in this commit.")

if __name__ == "__main__":
    main()
