import os
import subprocess
import sys
import argparse

PDF2JSON_SCRIPT = "pdf_2_jsonl.py"  # Change if you rename your script

import re

def sanitize_filename(name):
    # Replace spaces with underscores, remove special characters except dash, underscore, and dot
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "", name)
    return name

def convert_all_pdfs_in_dir(overwrite_all=False):
    pdf_files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found in the current directory.")
        return

    converted = 0
    skipped = 0

    for pdf in pdf_files:
        base = os.path.splitext(pdf)[0]
        safe_base = sanitize_filename(base)
        output_json = safe_base + ".json"
        if not overwrite_all and os.path.exists(output_json):
            print(f"Skipping {pdf} (already exists: {output_json})")
            skipped += 1
            continue

        print(f"Converting {pdf} to {output_json} ...")
        try:
            subprocess.run(
                [sys.executable, PDF2JSON_SCRIPT, pdf, output_json],
                check=True
            )
            converted += 1
        except subprocess.CalledProcessError as e:
            print(f"Error processing {pdf}: {e}")
    print(f"All done. Converted={converted}, Skipped={skipped}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Batch convert PDFs to JSON chunks."
    )
    parser.add_argument(
        "--overwrite-all",
        action="store_true",
        help="Overwrite existing .json outputs for all PDFs."
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    convert_all_pdfs_in_dir(overwrite_all=args.overwrite_all)
