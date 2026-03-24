import os
import subprocess
import sys
import argparse
import json
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PDF2JSON_SCRIPT = os.path.join(SCRIPT_DIR, "pdf_2_jsonl.py")
STAGE1_MANIFEST = "stage1_json_manifest.json"

import re

def sanitize_filename(name):
    # Replace spaces with underscores, remove special characters except dash, underscore, and dot
    name = name.replace(" ", "_")
    name = re.sub(r"[^\w\-.]", "", name)
    return name

def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def write_stage1_manifest(entries):
    payload = {
        "generated_at": utc_now_iso(),
        "generator": "batch_pdf_2_json.py",
        "cwd": os.getcwd(),
        "files": entries,
    }
    with open(STAGE1_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Manifest written: {STAGE1_MANIFEST} ({len(entries)} entries)")

def convert_all_pdfs_in_dir(overwrite_all=False):
    pdf_files = [f for f in os.listdir('.') if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found in the current directory.")
        write_stage1_manifest([])
        return

    pdf_files = sorted(pdf_files)
    converted = 0
    skipped = 0
    errors = 0
    manifest_entries = []

    for pdf in pdf_files:
        base = os.path.splitext(pdf)[0]
        safe_base = sanitize_filename(base)
        output_json = safe_base + ".json"
        if not overwrite_all and os.path.exists(output_json):
            print(f"Skipping {pdf} (already exists: {output_json})")
            skipped += 1
            manifest_entries.append(
                {
                    "pdf_file": pdf,
                    "output_json": output_json,
                    "status": "existing",
                    "exists": True,
                }
            )
            continue

        print(f"Converting {pdf} to {output_json} ...")
        try:
            subprocess.run(
                [sys.executable, PDF2JSON_SCRIPT, pdf, output_json],
                check=True
            )
            converted += 1
            manifest_entries.append(
                {
                    "pdf_file": pdf,
                    "output_json": output_json,
                    "status": "converted",
                    "exists": os.path.exists(output_json),
                }
            )
        except subprocess.CalledProcessError as e:
            print(f"Error processing {pdf}: {e}")
            errors += 1
            manifest_entries.append(
                {
                    "pdf_file": pdf,
                    "output_json": output_json,
                    "status": "error",
                    "exists": os.path.exists(output_json),
                }
            )
    write_stage1_manifest(manifest_entries)
    print(f"All done. Converted={converted}, Skipped={skipped}, Errors={errors}")


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
