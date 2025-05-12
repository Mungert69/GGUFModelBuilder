import numpy as np
import struct
import argparse
import subprocess
import json
import sys
import os
import tempfile
from pathlib import Path
# Ordered list of quant levels (lowest precision to highest)
quant_levels = [
    "IQ1_S", "IQ1_M",
    "IQ2_XXS", "IQ2_XS", "IQ2_S", 
    "Q2_K", 
    "IQ3_XXS",  "IQ3_S", 
    "Q3_K",
    "IQ4_NL", "IQ4_XS",
    "Q4_K",
    "Q5_K",
    "Q6_K",
    "Q8_0"
]
quant_groups = {
    "verylow": [
        "IQ1_S", "IQ1_M",
        "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ2_M"
        ],
    "low": [
        "Q2_K", "Q2_K_S",
        "IQ3_XXS", "IQ3_XS", "IQ3_S", "IQ3_M"
    ],
    "medium": [
        "Q3_K_S", "Q3_K", "Q3_K_L",
        "Q4_0", "Q4_1",
        "IQ4_NL", "IQ4_XS",
        "Q4_K_S", "Q4_K",     
    ],
    "high": [
        "Q5_0", "Q5_1", "Q5_K_S", "Q5_K",
        "Q6_K", "Q8_0"
    ]
}


def get_current_quant_types(gguf_file: str) -> dict:
    """Get quantization types using explicit file"""
    script_path = Path(__file__).parent / "get_gguf_tensor_info.py"
    output_file = Path("/tmp/gguf_quant_info.txt")  # Explicit path
    
    try:
        # Run script with explicit paths
        subprocess.run(
            [sys.executable, str(script_path), 
             str(Path(gguf_file).expanduser().resolve()),  # Handle ~ paths
             "-o", str(output_file)],
            check=True,
            timeout=30
        )
        
        # Read from explicit path
        quant_types = {}
        with open(output_file, "r") as f:
            for line in f:
                name, quant = line.strip().split("=")
                quant_types[name] = quant
                
        return quant_types
        
    except Exception as e:
        print(f"Error: Failed to read quantization info. File location: {output_file}")
        print(f"Details: {str(e)}")
        sys.exit(1)
def clean_tensor_name(name):
    """Remove .weight suffix and any whitespace/newlines"""
    return name.replace('.weight', '').strip()

def read_imatrix(file_path):
    weights = {}
    with open(file_path, "rb") as f:
        try:
            n_entries = struct.unpack('<i', f.read(4))[0]
            for _ in range(n_entries):
                name_len = struct.unpack('<i', f.read(4))[0]
                name = clean_tensor_name(f.read(name_len).decode('utf-8'))
                n_call = struct.unpack('<i', f.read(4))[0]
                n_values = struct.unpack('<i', f.read(4))[0]
                values = np.frombuffer(f.read(n_values * 4), dtype=np.float32)
                weights[name] = {'n_call': n_call, 'values': values}
            _ = struct.unpack('<i', f.read(4))[0]  # last_call
            input_filename_len = struct.unpack('<i', f.read(4))[0]
            _ = f.read(input_filename_len).decode('utf-8')
        except struct.error as e:
            print(f"Error reading imatrix file: {e}")
            return None
    return weights

def normalize_matrix(matrix):
    min_val, max_val = np.min(matrix), np.max(matrix)
    return np.zeros_like(matrix) if max_val - min_val == 0 else (matrix - min_val) / (max_val - min_val)

def determine_quant_tier(base_quant: str, mad: float, corr: float, 
                        mad_threshold: float = 0.002, corr_threshold: float = 0.95) -> tuple:
    """Returns (new_quant, bump_reason) tuple"""
    try:
        base_idx = quant_levels.index(base_quant)
    except ValueError:
        base_idx = quant_levels.index("Q4_K")

    def get_group(q):
        for group, items in quant_groups.items():
            if q in items:
                return group
        return "medium"

    group = get_group(base_quant)
    bump_reason = "No bump needed"

    # Adjust bump scale based on group
    if group == "verylow":
        bump_scale = 4
    elif group == "low":
        bump_scale = 3
    elif group == "medium":
        bump_scale = 2.0
    else:  # high
        bump_scale = 1

    # Determine bump amount and reason
    if mad > mad_threshold * 5 or corr < corr_threshold - 0.15:
        bump = int(2 * bump_scale)
        bump_reason = f"High sensitivity (MAD {mad:.4f} > {mad_threshold*5:.4f} or CORR {corr:.4f} < {corr_threshold-0.15:.4f})"
    elif mad > mad_threshold * 2.5 or corr < corr_threshold - 0.05:
        bump = int(1.5 * bump_scale)
        bump_reason = f"Moderate sensitivity (MAD {mad:.4f} > {mad_threshold*2.5:.4f} or CORR {corr:.4f} < {corr_threshold-0.05:.4f})"
    elif mad > mad_threshold or corr < corr_threshold:
        bump = int(1 * bump_scale)
        bump_reason = f"Low sensitivity (MAD {mad:.4f} > {mad_threshold:.4f} or CORR {corr:.4f} < {corr_threshold:.4f})"
    else:
        bump = 0
        bump_reason = "Within acceptable thresholds"

    new_idx = min(base_idx + bump, len(quant_levels) - 1)
    return quant_levels[new_idx], bump_reason
def compare_imatrix(file1, file2, gguf_file, mad_threshold=0.002, corr_threshold=0.95):
    weights1 = read_imatrix(file1)
    weights2 = read_imatrix(file2)
    current_quants = get_current_quant_types(gguf_file)
    
    if weights1 is None or weights2 is None or weights1.keys() != weights2.keys():
        print("Mismatch or error in imatrix files.")
        return

    total_mad, total_msd, total_corr, total_weights = 0.0, 0.0, 0.0, 0
    quant_suggestions = []

    for name in weights1:
        imatrix1 = weights1[name]['values']
        imatrix2 = weights2[name]['values']
        if len(imatrix1) != len(imatrix2):
            print(f"Skipping '{name}': mismatched sizes.")
            continue

        imatrix1_norm = normalize_matrix(imatrix1)
        imatrix2_norm = normalize_matrix(imatrix2)
        diff = imatrix1_norm - imatrix2_norm
        mad = np.mean(np.abs(diff))
        msd = np.mean(diff ** 2)
        corr = np.corrcoef(imatrix1_norm, imatrix2_norm)[0, 1]

        current_quant = current_quants.get(name, "Q4_K")  # Fallback if not found
        print(f"\nWeight: {name}")
        print(f"  Current Quant: {current_quant}")
        print(f"  MAD: {mad:.6f} (threshold: {mad_threshold:.6f})")
        print(f"  Corr: {corr:.6f} (threshold: {corr_threshold:.6f})")

        if mad > mad_threshold or corr < corr_threshold:
            suggested_quant, reason = determine_quant_tier(
                current_quant, mad, corr, 
                mad_threshold=mad_threshold,
                corr_threshold=corr_threshold
            )
            print(f"  -> Sensitive layer: {reason}")
            print(f"  Bump from {current_quant} to {suggested_quant}")
            quant_suggestions.append((name, suggested_quant))
        else:
            print("  -> Within thresholds, keeping current quantization")

        total_mad += mad
        total_msd += msd
        total_corr += corr
        total_weights += 1

    print("\n=== Suggested --tensor-type arguments (copy-ready) ===")
    tensor_args = " ".join([f"--tensor-type {name}={quant}" for name, quant in quant_suggestions])
    print(tensor_args)

    if total_weights > 0:
        print("\n=== Summary ===")
        print(f"Avg MAD: {total_mad / total_weights:.6f}")
        print(f"Avg MSD: {total_msd / total_weights:.6f}")
        print(f"Avg Corr: {total_corr / total_weights:.6f}")
    else:
        print("No weights compared.")

def main():
    parser = argparse.ArgumentParser(
        description="Compare two .imatrix files and recommend tensor quant types using actual model quantization"
    )
    parser.add_argument("file1", help="Reference .imatrix file (baseline)")
    parser.add_argument("file2", help="Test .imatrix file to compare against baseline")
    parser.add_argument("gguf_file", help="GGUF model file to read current quantization types from")
    parser.add_argument("--mad-threshold", type=float, default=0.002, 
                       help="MAD threshold to consider a layer sensitive")
    parser.add_argument("--corr-threshold", type=float, default=0.95, 
                       help="Correlation threshold to consider a layer sensitive")
    args = parser.parse_args()

    compare_imatrix(
        file1=args.file1,
        file2=args.file2,
        gguf_file=args.gguf_file,
        mad_threshold=args.mad_threshold,
        corr_threshold=args.corr_threshold
    )

if __name__ == "__main__":
    main()
