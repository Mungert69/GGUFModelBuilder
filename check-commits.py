import os
import json
import logging
import requests
from datetime import datetime
from llama_cpp import Llama, LlamaGrammar

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO  # Logging level is set to INFO
)

# GitHub API settings
GITHUB_REPO = "ggml-org/llama.cpp"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
LAST_COMMIT_FILE = "last_commit.txt"
GITHUB_TOKEN = "your_personal_access_token_here"  # Add your token here
HEADERS = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
# Local GGUF model
LOCAL_MODEL_PATH = "./Llama-3.1-8B-Instruct-q4_k_l.gguf"
GRAMMAR_FILE_PATH = "./llama.cpp/grammars/json.gbnf"  # Path to your JSON grammar file

# Load quantized GGUF model using llama-cpp-python
logging.info("Loading quantized GGUF model...")
try:
    llm = Llama(
        model_path=LOCAL_MODEL_PATH,  # Path to the model
        n_ctx=8048,  # Set the context window size to 8048 tokens
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

def fetch_latest_commit():
    """Fetch latest commit from GitHub API and return its details, including file changes and diffs."""
    logging.info(f"Fetching latest commit from {GITHUB_REPO}...")
    try:
        # Fetch the latest commit SHA
        response = requests.get(GITHUB_API_URL, timeout=10)
        response.raise_for_status()
        commits = response.json()
        if not commits:
            logging.warning("No commits found!")
            return None
        latest_commit_sha = commits[0]["sha"]

        # Fetch the commit details, including file changes and diffs
        commit_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{latest_commit_sha}"
        commit_response = requests.get(commit_url, timeout=10)
        commit_response.raise_for_status()
        latest_commit = commit_response.json()

        logging.info(f"Latest commit data: {json.dumps(latest_commit, indent=2)}")
        return latest_commit

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

    # Extract file names and diffs
    file_changes = []
    for file in files:
        filename = file.get("filename", "")
        patch = file.get("patch", "")  # Unified diff for the file
        file_changes.append({"filename": filename, "patch": patch})

    logging.info(f"File changes: {json.dumps(file_changes, indent=2)}")

    # Prepare the prompt with only the commit message, file names, and diffs
    prompt = (
        "Commit message:\n\"{message}\"\n"
        "File changes:\n{file_changes}\n"
        "---\n"
        "You are an AI assistant. Analyze the above commit message and file changes to determine if it adds a new AI model.\n"
        "Respond ONLY in valid JSON format. Your response must be a complete JSON object with no extra text.\n"
        "The response should look like this:\n"
        "{{\n"
        '  "is_new_model": true/false,\n'
        '  "model_name_if_found": "Name of the model if detected, otherwise null",\n'
        '  "reason_for_answer": "Explain why or why not."\n'
        "}}"
    ).format(message=message, file_changes=json.dumps(file_changes, indent=2))
   
    try:
        llm_response = llm(
            prompt,
            max_tokens=300,  # Adjust token size if needed
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

def find_huggingface_model(model_name):
    """Search for the model on Hugging Face and return its ID."""
    api = HfApi()
    models = api.list_models(search=model_name)
    if models:
        return models[0].modelId  # Return the first match
    return None

def download_model(huggingface_model_id):
    """Download model from Hugging Face and convert it to GGUF format."""
    logging.info(f"Downloading model {huggingface_model_id} from Hugging Face...")
    try:
        os.system(f"huggingface-cli download {huggingface_model_id} --local-dir {LOCAL_MODEL_DIR}")
        logging.info("Download completed.")

        logging.info("Converting to GGUF format...")
        os.system(f"python3 ./convert-llama3-to-gguf.py --input {LOCAL_MODEL_DIR} --output {LOCAL_MODEL_PATH}")
        logging.info("Conversion to GGUF completed.")
    except Exception as e:
        logging.error(f"Model download or conversion failed: {e}")

def fetch_last_50_commits():
    """Fetch the last 50 commits from GitHub API and return their details, including file changes and diffs."""
    logging.info(f"Fetching last 50 commits from {GITHUB_REPO}...")
    try:
        # Fetch the last 50 commits
        params = {"per_page": 50}  # Fetch up to 50 commits
        response = requests.get(GITHUB_API_URL, params=params, timeout=10)
        response.raise_for_status()
        commits = response.json()
        if not commits:
            logging.warning("No commits found!")
            return None

        logging.info(f"Fetched {len(commits)} commits from GitHub API.")

        # Fetch details for each commit
        commit_details = []
        for commit in commits:
            commit_sha = commit["sha"]
            commit_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{commit_sha}"
            commit_response = requests.get(commit_url, timeout=10)
            commit_response.raise_for_status()
            commit_details.append(commit_response.json())

        logging.info(f"Fetched details for {len(commit_details)} commits.")
        return commit_details

    except requests.RequestException as e:
        logging.error(f"GitHub API error: {e}")
        return None
def main():
    """Main monitoring function."""
    last_commit = None
    if os.path.exists(LAST_COMMIT_FILE):
        with open(LAST_COMMIT_FILE, "r") as f:
            last_commit = f.read().strip()
        logging.info(f"Last processed commit SHA: {last_commit}")
    else:
        logging.info("No last processed commit found. Starting from the latest commit.")

    # Fetch the last 50 commits
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

        # Analyze the commit
        is_new_model, model_name = analyze_commit(commit)
        if is_new_model and model_name:
            huggingface_model_id = find_huggingface_model(model_name)
            if huggingface_model_id:
                logging.info(f"Found Hugging Face model ID: {huggingface_model_id}")
                with open("huggingface_model_id.txt", "w") as f:
                    f.write(huggingface_model_id)
                logging.info("New model detected! Downloading and converting...")
                download_model(huggingface_model_id)
                with open(LAST_COMMIT_FILE, "w") as f:
                    f.write(commit_sha)
                break  # Stop after processing the first new model
            else:
                logging.info(f"No Hugging Face model found for {model_name}.")
        else:
            logging.info("No model-related changes detected in this commit.")
if __name__ == "__main__":
    main()
