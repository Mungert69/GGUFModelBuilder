import os
import subprocess
import sys

PDF2JSON_SCRIPT = "pdf_2_jsonl.py"  # Change if you rename your script

import re

def sanitize_filename(name):
    # Replace spaces with underscores, remove special characters except dash, underscore, and dot
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "", name)
    return name

def convert_all_pdfs_in_dir():
    pdf_files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found in the current directory.")
        return

    for pdf in pdf_files:
        base = os.path.splitext(pdf)[0]
        safe_base = sanitize_filename(base)
        output_json = safe_base + ".json" 
        print(f"Converting {pdf} to {output_json} ...")
        try:
            subprocess.run(
                [sys.executable, PDF2JSON_SCRIPT, pdf, output_json],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error processing {pdf}: {e}")
    print("All done.")

if __name__ == "__main__":
    convert_all_pdfs_in_dir()

