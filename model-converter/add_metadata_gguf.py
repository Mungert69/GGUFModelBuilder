#!/usr/bin/env python3
import os
import sys
import shutil
import tempfile
from pathlib import Path
import subprocess
import argparse

def add_metadata(input_file_path: str, overrides: list[str] = None, override_file: str = None):
    """
    Adds metadata to the GGUF file specified by input_file_path.
    
    Args:
        input_file_path (str): Path to the input GGUF file
        overrides (list): List of override strings (key=type:value)
        override_file (str): Path to file containing overrides
    """
    input_file = Path(input_file_path)
    if not input_file.is_file():
        print(f"The specified input GGUF file {input_file} does not exist.")
        sys.exit(1)

    # Paths and file locations
    script_dir = Path(__file__).parent
    src_script = script_dir / "update_gguf.py"

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

    # Add override arguments if provided
    if overrides:
        for override in overrides:
            cmd.extend(["--override", override])
    if override_file:
        cmd.extend(["--override-file", override_file])

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
    parser = argparse.ArgumentParser(description="Add metadata to GGUF file")
    parser.add_argument("input", help="Input GGUF file")
    parser.add_argument("--override", action="append", 
                      help="Override metadata (key=type:value)",
                      metavar="glm4.rope.dimension_count=int:64")
    parser.add_argument("--override-file", 
                      help="File containing metadata overrides",
                      metavar="overrides.txt")
    args = parser.parse_args()

    add_metadata(
        input_file_path=args.input,
        overrides=args.override,
        override_file=args.override_file
    )

if __name__ == "__main__":
    main()
