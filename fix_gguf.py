import os
import sys
from gguf import GGUFReader, GGUFWriter

# Configuration: Set new metadata values
NEW_UNKNOWN_TOKEN_ID = 3251
NEW_PADDING_TOKEN_ID = 200029
NEW_CHAT_TEMPLATE = """{% for message in messages %}{% if message['role'] == 'system' and 'tools' in message and message['tools'] is not none %}{{ '<|' + message['role'] + '|>' + message['content'] + '<|tool|>' + message['tools'] + '<|/tool|>' + '<|end|>' }}{% else %}{{ '<|' + message['role'] + '|>' + message['content'] + '<|end|>' }}{% endif %}{% endfor %}{% if add_generation_prompt %}{{ '<|assistant|>' }}{% endif %}"""

# Input and output directories
INPUT_DIR = "./input_gguf"  # Change to your input folder
OUTPUT_DIR = "./output_gguf"  # Change to your output folder

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def update_gguf_metadata(input_file, output_file):
    """Updates GGUF metadata and saves the updated file to the output directory."""
    print(f"Processing: {input_file}")

    try:
        reader = GGUFReader(input_file)

        # Extract the architecture type (required by GGUFWriter)
        arch = reader.metadata.get("general.arch", "unknown")
        if arch == "unknown":
            print(f"⚠️ Warning: Could not determine architecture for {input_file}")

        writer = GGUFWriter(output_file, arch=arch)

        # Copy existing metadata
        writer.metadata = reader.metadata

        # Update metadata fields
        writer.metadata["tokenizer.ggml.unknown_token_id"] = NEW_UNKNOWN_TOKEN_ID
        writer.metadata["tokenizer.ggml.padding_token_id"] = NEW_PADDING_TOKEN_ID
        writer.metadata["tokenizer.chat_template"] = NEW_CHAT_TEMPLATE

        # Write new GGUF file with updated metadata
        writer.write(reader.tensors)
        print(f"✅ Updated GGUF saved: {output_file}")

    except Exception as e:
        print(f"❌ Error updating {input_file}: {e}")

# Iterate over all GGUF files in the input directory
if __name__ == "__main__":
    if not os.path.exists(INPUT_DIR):
        print(f"❌ Input directory '{INPUT_DIR}' not found!")
        sys.exit(1)

    files_processed = 0

    for filename in os.listdir(INPUT_DIR):
        if filename.endswith(".gguf"):
            input_path = os.path.join(INPUT_DIR, filename)
            output_path = os.path.join(OUTPUT_DIR, filename)

            update_gguf_metadata(input_path, output_path)
            files_processed += 1

    if files_processed == 0:
        print("⚠️ No GGUF files found in the input directory.")
    else:
        print(f"🎉 Finished processing {files_processed} GGUF files.")

