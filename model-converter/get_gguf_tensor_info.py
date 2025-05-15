#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
import gguf

def clean_tensor_name(name):
    """Consistent name cleaning across both scripts"""
    return name.replace('.weight', '').strip()

def main():
    parser = argparse.ArgumentParser(description="Get GGUF tensor quantization types")
    parser.add_argument("gguf_file", help="Input GGUF file")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    args = parser.parse_args()

    try:
        reader = gguf.GGUFReader(args.gguf_file)
        with open(args.output, "w") as f:
            for tensor in reader.tensors:
                clean_name = clean_tensor_name(tensor.name)
                f.write(f"{clean_name}={tensor.tensor_type.name}\n")
        print(f"Quantization data written to: {args.output}")
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
