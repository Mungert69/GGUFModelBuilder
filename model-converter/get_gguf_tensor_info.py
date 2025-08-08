#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Prefer local gguf if available
import sys
from pathlib import Path
local_gguf_path = Path.home() / "code/models/llama.cpp/gguf-py"
if (local_gguf_path / "gguf").exists():
    sys.path.insert(0, str(local_gguf_path))
import gguf

def clean_tensor_name(name):
    """Consistent name cleaning across both scripts"""
    return name.replace('.weight', '').strip()

def main():
    parser = argparse.ArgumentParser(description="Get GGUF tensor quantization types")
    parser.add_argument("gguf_file", help="Input GGUF file")
    parser.add_argument("-o", "--output", required=True, help="Output file path")
    args = parser.parse_args()

    import traceback
    try:
        reader = gguf.GGUFReader(args.gguf_file)
    except Exception as e:
        print("Error initializing GGUFReader:")
        traceback.print_exc()
        sys.exit(1)

    try:
        with open(args.output, "w") as f:
            for tensor in reader.tensors:
                clean_name = clean_tensor_name(tensor.name)
                raw_value = tensor.tensor_type
                try:
                    quant_type = tensor.tensor_type.name
                except Exception:
                    quant_type = "UNKNOWN"
                print(f"{clean_name}: quant_type={quant_type}, raw_value={raw_value}")
                f.write(f"{clean_name}={quant_type} ({raw_value})\n")
        print(f"Quantization data written to: {args.output}")
    except Exception as e:
        print("Error during tensor processing or writing:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
