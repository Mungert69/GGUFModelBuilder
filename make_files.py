import os
import json
import re
import math
import subprocess
import argparse
import urllib.request
from update_readme import update_readme  # Importing the update_readme function
import shutil
from huggingface_hub import HfApi, login
from dotenv import load_dotenv
from pathlib import Path

# Load the .env file
load_dotenv()

# Read the API token from the .env file
api_token = os.getenv("HF_API_TOKEN")

if not api_token:
    print("Error: Hugging Face API token not found in .env file.")
    exit()

# Authenticate with the Hugging Face Hub
try:
    login(token=api_token)
    print("Authentication successful.")
except Exception as e:
    print(f"Authentication failed: {e}")
    exit()

# Initialize Hugging Face API
api = HfApi()

IMATRIX_BASE_URL = "https://huggingface.co/bartowski/"

# Load QUANT_CONFIGS from JSON file
quant_file = Path("quant_configs.json")
if quant_file.exists():
    with quant_file.open("r") as file:
        quant_data = json.load(file)
else:
    print(f"Error: Quantization config file '{quant_file}' not found.")
    exit()

# Convert each configuration dictionary to a tuple with the same structure as before
QUANT_CONFIGS = [
    (
        item["name"],
        item["type"],
        item["embed_type"],
        item["output_type"],
        item["use_imatrix"],
        item["use_pure"]
    )
    for item in quant_data
]

# Print loaded configurations
print("Loaded QUANT_CONFIGS:")
for config in QUANT_CONFIGS:
    print(config)

QUANT_BIT_LEVELS = {
    # 1-bit quantizations (very aggressive)
    "IQ1_S": 1, "IQ1_M": 1, 
    # 2-bit quantizations
    "Q2_K": 2, "Q2_K_S": 2, "Q2_K_M": 2, "IQ2_XS": 2, "IQ2_S": 2, "IQ2_M": 2, "IQ2_XXS": 2, 
    # 3-bit quantizations
    "Q3_K": 3, "Q3_K_S": 3, "Q3_K_M": 3, "IQ3_XS": 3, "IQ3_S": 3, "IQ3_M": 3, "IQ3_XXS": 3,
    # 4-bit and up
    "Q4_K": 4, "Q4_K_S": 4, "Q4_K_M": 4, "IQ4_XS": 4, "IQ4_NL": 4, "Q4_0": 4, "Q4_1": 4,
    "Q5_K": 5, "Q5_K_S": 5, "Q5_K_M": 5, "Q5_0": 5, "Q5_1" : 5,
    "Q6_K": 6, "Q8_0": 8, "F16": 16, "BF16": 16
}
def get_standard_chunk_name(base_name, quant_type, part_num, total_parts):
    """Generate HF-standard chunk names with validation"""
    # Clean the base name by removing existing quantization suffixes
    clean_base = re.sub(r'-(f16|bf16|q[0-9]_[kmls]|iq\d_\w+)$', '', base_name, flags=re.IGNORECASE)
    
    # Validate and convert part numbers
    try:
        part_num = int(part_num)
        total_parts = int(total_parts)
    except (ValueError, TypeError):
        raise ValueError("Part numbers must be integers")
    
    return f"{clean_base}-{quant_type}-{part_num:05d}-of-{total_parts:05d}.gguf"


def split_file_standard(file_path, quant_type, chunk_size=45*1024**3):
    """Robust file splitting with proper error handling"""
    file_name = os.path.basename(file_path)
    base_name = file_name.replace('.gguf', '')
    
    # Initialize variables
    chunk_paths = []
    part_num = 1
    read_size = 1 * 1024**3  # 1GB read buffer
    safe_chunk_size = int(chunk_size * 0.95)  # 5% safety buffer

    try:
        # First pass to determine total chunks needed
        with open(file_path, 'rb') as f:
            total_size = os.path.getsize(file_path)
            total_parts = math.ceil(total_size / safe_chunk_size)
        
        # Second pass for actual splitting
        with open(file_path, 'rb') as f:
            for current_part in range(1, total_parts + 1):
                chunk_name = get_standard_chunk_name(base_name, quant_type, current_part, total_parts)
                chunk_path = os.path.join(os.path.dirname(file_path), chunk_name)
                
                bytes_written = 0
                with open(chunk_path, 'wb') as chunk_file:
                    while bytes_written < safe_chunk_size:
                        data = f.read(min(read_size, safe_chunk_size - bytes_written))
                        if not data:
                            break
                        chunk_file.write(data)
                        bytes_written += len(data)
                
                chunk_paths.append(chunk_path)
                
                # Check if we've reached EOF
                if bytes_written < safe_chunk_size:
                    break
        
        return chunk_paths

    except Exception as e:
        # Cleanup any partial files
        for chunk in chunk_paths:
            try:
                os.remove(chunk)
            except:
                pass
        raise RuntimeError(f"Failed to split file: {str(e)}")

def extract_quant_folder_name(filename):
    """Extract the quantization part from filename to use as folder name"""
    # Remove .gguf extension if present
    base_name = filename.replace('.gguf', '')
    
    # Pattern to match quantization suffixes (bf16-q4_k, q3_k_l, etc.)
    patterns = [
        r'(?:.*-)?(bf16-[^\-]+)$',  # Matches bf16-* at end
        r'(?:.*-)?([^\-]+)$',       # Matches last part if no bf16
    ]
    
    for pattern in patterns:
        match = re.search(pattern, base_name)
        if match:
            return match.group(1)
    
    # Fallback to entire filename if no match
    return base_name


def upload_file_to_hf(file_path, repo_id, create_dir=False):
    """Upload a file to Hugging Face Hub with optional subdirectory organization.
    
    Args:
        file_path: Local path to the file
        repo_id: HF repository ID (e.g., "username/repo")
        create_dir: If True, organizes files in quant-type subfolders
    """
    try:
        filename = os.path.basename(file_path)
        
        if create_dir:
            # Extract quantization folder name (e.g., "q4_k" from "model-q4_k.gguf")
            folder_name = extract_quant_folder_name(filename)
            path_in_repo = f"{folder_name}/{filename}"
            
            # Check/create folder (HF API automatically handles path creation)
            print(f"📂 Organizing in subfolder: {folder_name}/")
        else:
            path_in_repo = filename  # Default: root directory

        api.upload_file(
            path_or_fileobj=file_path,
            path_in_repo=path_in_repo,  # Now includes directory if create_dir=True
            repo_id=repo_id,
            token=api_token,
        )
        return True
    except Exception as e:
        print(f"❌ Error uploading {filename}: {e}")
        return False

def upload_large_file(file_path, repo_id, quant_type):
    """Enhanced upload with detailed error reporting"""
    try:
        file_size = os.path.getsize(file_path)
        print(f"\n📦 Processing: {os.path.basename(file_path)} ({file_size/1024**3:.2f}GB)")
        
        if file_size <= 49.5 * 1024**3:
            print("🔼 Direct upload (under 49.5GB)")
            return upload_file_to_hf(file_path, repo_id)
            
        print("🔪 Splitting large file...")
        chunks = split_file_standard(file_path, quant_type)
        print(f"✂ Created {len(chunks)} chunks")
        
        for idx, chunk in enumerate(chunks, 1):
            print(f"⤴ Uploading chunk {idx}/{len(chunks)} ({os.path.basename(chunk)})")
            if not upload_file_to_hf(chunk, repo_id, create_dir=True):
                raise RuntimeError(f"Chunk {idx} upload failed")
            os.remove(chunk)
            print(f"✅ Chunk {idx} uploaded and cleaned")
            
        return True
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print(f"⚠ Keeping original file: {file_path}")
        return False

def get_model_size(base_name):
    """Enhanced model size extraction from name with better pattern matching"""
    import re
    
    # Common patterns in model names
    patterns = [
        r'(\d+\.?\d*)\s*([bm])b?',  # Matches "7b", "1.5b", "350m"
        r'-(\d+)([bm])-',           # Matches "-7b-", "-350m-"
        r'_(\d+)([bm])_',           # Matches "_7b_", "_350m_"
        r'(\d+)([bm])\D',           # Matches "7b-", "350m_"
        r'(\d+)([bm])$',            # Matches "7b", "350m" at end
    ]
    
    for pattern in patterns:
        match = re.search(pattern, base_name, re.IGNORECASE)
        if match:
            size = float(match.group(1))
            size_unit = match.group(2).lower()
            if size_unit == 'b':  # Billion
                return int(size * 1e9)
            elif size_unit == 'm':  # Million
                return int(size * 1e6)
    
    print(f"⚠ Couldn't determine model size from name: {base_name}")
    return None

def filter_quant_configs(base_name, configs):
    """Filter quantization configs based on model size, adding TQ quants if 'TriLM' is in the name."""
    model_size = get_model_size(base_name)
    if not model_size:
        print("⚠ Couldn't determine model size from name. Using all quantizations.")
        return configs

    min_bits = 3 if model_size < 3e9 else (  # <4B models
                2 if model_size < 10e9 else   # 4-10B models
                1)                           # 10B+ models

    filtered = []
    for config in configs:
        quant_type = config[1]
        bits = QUANT_BIT_LEVELS.get(quant_type, 16)

        if bits >= min_bits and (not quant_type.startswith("TQ") or "TriLM" in base_name):
            filtered.append(config)
        else:
            print(f"⚠ Skipping {quant_type} ({bits}bit) for {base_name} "
                  f"({model_size/1e9:.1f}B) - too aggressive")

    return filtered

def build_imatrix_urls(company_name, model_name):
    """Build possible URLs for the .imatrix file using the company name and model name."""
    company_name_parts = company_name.split("-")
    first_part_company_name_cap = company_name_parts[0].capitalize()
    model_name_parts = model_name.split("-")
    if model_name_parts[0] == first_part_company_name_cap:
        model_name_corrected = "-".join(model_name_parts[1:])
    else:
        model_name_corrected = model_name
    model_name_1 = f"{first_part_company_name_cap}-{model_name_corrected}"
    model_name_2 = f"{company_name}_{model_name}"
    return [
        f"{IMATRIX_BASE_URL}{model_name}-GGUF/resolve/main/{model_name}.imatrix",
        f"{IMATRIX_BASE_URL}{model_name_1}-GGUF/resolve/main/{model_name_1}.imatrix",
        f"{IMATRIX_BASE_URL}{model_name_2}-GGUF/resolve/main/{model_name_2}.imatrix"
    ]

def download_imatrix(input_dir, company_name, model_name):
    """Download or generate the .imatrix file and upload it to Hugging Face Hub."""
    parent_dir = os.path.abspath(os.path.join(input_dir, os.pardir))  # This properly gets parent
    imatrix_dir = os.path.join(parent_dir, "imatrix-files")
    imatrix_file_copy = os.path.join(imatrix_dir, f"{model_name}.imatrix")
    imatrix_file = os.path.join(input_dir, f"{model_name}.imatrix")
    
    if os.path.exists(imatrix_file_copy):
        print(f"Found existing .imatrix file in 'imatrix-files' directory: {imatrix_file_copy}")
        shutil.copy(imatrix_file_copy, imatrix_file)
        print(f"Copied .imatrix file to model's folder: {imatrix_file}")
        return imatrix_file
    
    if not os.path.exists(imatrix_file):
        print(f"{imatrix_file} not found. Attempting to download...")
        urls = build_imatrix_urls(company_name, model_name)
        downloaded = False
        for url in urls:
            try:
                print(f"Trying: {url}")
                urllib.request.urlretrieve(url, imatrix_file)
                print(f"Successfully downloaded .imatrix from {url}")
                downloaded = True
                break
            except Exception as e:
                print(f"Failed to download from {url}: {e}")

        if not downloaded:
            print("All download attempts failed. Generating imatrix locally...")
            bf16_model_path = os.path.join(input_dir, f"{model_name}-bf16.gguf")
            if not os.path.exists(bf16_model_path):
                raise FileNotFoundError(f"Cannot generate imatrix: {bf16_model_path} not found")
            imatrix_train_set = "imatrix-train-set"
            command = [
                "./llama.cpp/llama-imatrix",
                "-m", bf16_model_path,
                "-f", imatrix_train_set,
                "-o", imatrix_file
            ]
            print("Running:", " ".join(command))
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                print("Error generating imatrix:")
                print(result.stderr)
                raise RuntimeError("Failed to generate imatrix file")
            else:
                print("Successfully generated imatrix file")
                os.makedirs(imatrix_dir, exist_ok=True)
                shutil.copy(imatrix_file, imatrix_file_copy)
                print(f"Saved a copy of the imatrix file to: {imatrix_file_copy}")
    
    else:
        print(f"{imatrix_file} already exists. Skipping download.")
    
    return imatrix_file

def create_repo_if_not_exists(repo_id, api_token):
    """Check if the repository exists, and create it if it doesn't."""
    api = HfApi()
    try:
        api.create_repo(repo_id, exist_ok=True, token=api_token)
        print(f"Repository {repo_id} is ready.")
        return True
    except Exception as e:
        print(f"Error creating repository: {e}")
        return False

def needs_compatibility_check(quant_type, tensor_type, embed_type):
    """Determine if we need to check compatibility for Q5_K/Q6_K tensor/embed types"""
    return (tensor_type in ["Q5_K", "Q6_K"] or 
            embed_type in ["Q5_K", "Q6_K"])

def quantize_with_fallback(model_path, output_path, quant_type, tensor_type=None, embed_type=None, 
                         use_imatrix=None, use_pure=False):
    """Perform quantization with automatic fallback for Q5_K/Q6_K tensor/embed types"""
    temp_output = f"{output_path}.tmp"
    
    def run_quantization(t_type, e_type):
        """Helper function to run quantization with specific types"""
        command = ["./llama.cpp/llama-quantize"]
        if use_imatrix:
            command.extend(["--imatrix", use_imatrix])
        if use_pure:
            command.append("--pure")
        if t_type and e_type:
            command.extend(["--output-tensor-type", t_type])
            command.extend(["--token-embedding-type", e_type])
        command.extend([model_path, temp_output, quant_type])
        
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stdout:
            print("Output:", result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        return result

    # First try with original types
    if not needs_compatibility_check(quant_type, tensor_type, embed_type):
        result = run_quantization(tensor_type, embed_type)
        if result.returncode == 0:
            os.rename(temp_output, output_path)
            return True
        print(f"⚠ Quantization failed with unexpected error:")
        print(result.stderr)
        return False

    # Try with original Q5_K/Q6_K types first
    result = run_quantization(tensor_type, embed_type)
    if result.returncode == 0:
        os.rename(temp_output, output_path)
        return True
    
    # If failed, try with Q5_1 fallback for tensor/embed types
    print(f"⚠ Q5_K/Q6_K tensor/embed types not compatible, falling back to Q5_1")
    adjusted_tensor = tensor_type if tensor_type not in ["Q5_K", "Q6_K"] else "Q5_1"
    adjusted_embed = embed_type if embed_type not in ["Q5_K", "Q6_K"] else "Q5_1"
    
    result = run_quantization(adjusted_tensor, adjusted_embed)
    if result.returncode == 0:
        os.rename(temp_output, output_path)
        return True
    
    print(f"❌ Quantization failed even with fallback:")
    print(result.stderr)
    try:
        os.remove(temp_output)
    except:
        pass
    return False

def quantize_model(input_model, company_name, base_name):
    """Quantize the model and upload files following HF standards."""
    # Setup paths and directories
    input_dir = os.path.dirname(input_model)
    output_dir = input_dir
    bf16_model_file = os.path.join(input_dir, f"{base_name}-bf16.gguf")
    imatrix_file = download_imatrix(input_dir, company_name, base_name)
    repo_id = f"Mungert/{base_name}-GGUF"

    # Validate BF16 model exists
    if not os.path.exists(bf16_model_file):
        raise FileNotFoundError(f"BF16 model not found: {bf16_model_file}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Get filtered quantization configs
    filtered_configs = filter_quant_configs(base_name, QUANT_CONFIGS)
    print(f"🏗 Selected {len(filtered_configs)} quantizations for {base_name}")
    
    # Initialize repo tracking
    repo_created = False
    # Track if we've created any IQ1/IQ2 files
    has_iq1_iq2_files = False

    # Process each quantization config
    for suffix, quant_type, tensor_type, embed_type, use_imatrix, use_pure in filtered_configs:
        output_file = f"{base_name}-{suffix}.gguf"
        output_path = os.path.join(output_dir, output_file)
       
        print(f"\n🏗 Processing {output_file}...")
        success = quantize_with_fallback(
            bf16_model_file,
            output_path,
            quant_type,
            tensor_type=tensor_type,
            embed_type=embed_type,
            use_imatrix=imatrix_file if use_imatrix else None,
            use_pure=use_pure
        )
        
        if not success:
            continue

        print(f"Successfully created {output_file} in {output_dir}")
        
        # Check if this is an IQ1/IQ2 file
        if not has_iq1_iq2_files and any(quant_type.startswith(prefix) for prefix in ['IQ1', 'IQ2']):
            has_iq1_iq2_files = True
        
        # Create repo on first successful quantization
        if not repo_created:
            if create_repo_if_not_exists(repo_id, api_token):
                repo_created = True
            else:
                print("Failed to create repository. Aborting further uploads.")
                break
        
        # Handle file upload with standardized large file support
        if repo_created:
            if upload_large_file(output_path, repo_id, quant_type):
                print(f"Uploaded {output_file} successfully.")
                try:
                    os.remove(output_path)
                    print(f"Deleted {output_file} to free space.")
                except Exception as e:
                    print(f"Warning: Could not delete {output_file}: {e}")
            else:
                print(f"Failed to upload {output_file}. Keeping local file.")
    
    # Upload imatrix file if repository was created
    if os.path.exists(imatrix_file) and repo_created:
        if upload_large_file(imatrix_file, repo_id, "imatrix"):
            print(f"Uploaded {os.path.basename(imatrix_file)} successfully.")
            try:
                os.remove(imatrix_file)
                print(f"Deleted {os.path.basename(imatrix_file)} to free space.")
            except Exception as e:
                print(f"Warning: Could not delete {imatrix_file}: {e}")
        else:
            print(f"Failed to upload {os.path.basename(imatrix_file)}. Keeping local file.")
    
    # Update README after all files are processed
    try:
        print("\n📝 Updating README.md...")
        update_readme(input_dir, base_name, add_iquant_txt=has_iq1_iq2_files)
    except Exception as e:
        print(f"⚠ Failed to update README: {e}")

def main():
    parser = argparse.ArgumentParser(description="Automate GGUF model quantization")
    parser.add_argument("model_id", help="Full Hugging Face model ID (e.g., 'company/model')")
    args = parser.parse_args()

    if "/" not in args.model_id:
        print("Error: Model ID must be in the format 'company_name/model_name'.")
        exit(1)

    company_name, model_name = args.model_id.split("/", 1)
    model_dir = os.path.join(os.getcwd(), model_name)
    quantize_model(os.path.join(model_dir, f"{model_name}-bf16.gguf"), company_name, model_name)

if __name__ == "__main__":
    main()

