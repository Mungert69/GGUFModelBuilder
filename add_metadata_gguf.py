#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
from pathlib import Path
import subprocess

def add_metadata(input_file: Path):
    """
    Adds metadata to the GGUF file specified by input_file.
    
    Args:
        input_file (Path): Path to the input GGUF file.
    """
    if not input_file.is_file():
        print(f"The specified input GGUF file {input_file} does not exist.")
        sys.exit(1)

    # Paths and file locations
    script_dir = Path(__file__).parent
    src_script = script_dir / "update_gguf.py"  # Update this if needed

    gguf_dir = Path.home() / "code" / "models" / "llama.cpp" / "gguf-py"
    dest_dir = gguf_dir / "gguf" / "scripts"

    if not dest_dir.exists():
        print(f"Destination directory '{dest_dir}' does not exist. Exiting.")
        sys.exit(1)

    dest_script = dest_dir / "update_gguf.py"

    # Copy the update_gguf.py script to the expected directory
    try:
        shutil.copy(src_script, dest_script)
        print(f"Copied {src_script} to {dest_script}")
    except Exception as e:
        print(f"Failed to copy script: {e}")
        sys.exit(1)

    # Create a temporary file for output
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_output_file = Path(temp_file.name)
        print(f"Created temporary output file: {temp_output_file}")

    # Prepare the command to run the update_gguf.py script
    cmd = [
        sys.executable,             # uses the current Python interpreter
        str(dest_script),           # path to update_gguf.py at the destination
        str(input_file),            # the original input GGUF file
        str(temp_output_file),      # temporary output file
        "--force"                   # bypass warnings; adjust as needed
    ]

    # Change to the destination directory so the relative imports work correctly
    os.chdir(dest_dir)

    # Execute the update_gguf.py script
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("Execution output:")
        print(result.stdout)
        if result.stderr:
            print("Execution errors:")
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Script execution failed with return code {e.returncode}")
        print(e.output)
        sys.exit(e.returncode)

    # After script finishes, delete the original file and rename the temp output file to the original file name
    try:
        print(f"Deleting original file: {input_file}")
        os.remove(input_file)
        print(f"Renaming temporary file to original file name: {input_file}")
        temp_output_file.rename(input_file)
        print(f"Renamed {temp_output_file} to {input_file}")
    except Exception as e:
        print(f"Failed to replace the original file: {e}")
        sys.exit(1)

def main():
    # Check for an input argument (GGUF input file)
    if len(sys.argv) != 2:
        print("Usage: python3 add_metadata_gguf.py <input_gguf_file>")
        sys.exit(1)

    # Path to the input GGUF file (received as argument)
    input_file = Path(sys.argv[1])
    add_metadata(input_file)

if __name__ == "__main__":
    main()

