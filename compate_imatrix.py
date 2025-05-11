import numpy as np
import struct
import matplotlib.pyplot as plt

# Ordered list of quant levels (lowest precision to highest)
quant_levels = [
    "IQ1_S", "IQ1_M", "TQ1_0", "TQ2_0", "IQ2_XXS", "IQ2_XS", "IQ2_S", "IQ2_M",
    "IQ3_XXS", "IQ3_XS", "IQ3_S", "IQ3_M",
    "Q2_K", "Q2_K_S",
    "Q3_K_S", "Q3_K_M", "Q3_K_L",
    "Q4_0", "Q4_1",
    "Q4_K_S", "Q4_K_M",
    "Q5_0", "Q5_1", "Q5_K_S", "Q5_K_M",
    "Q6_K", "Q8_0",
    "F16", "BF16", "F32"
]

def read_imatrix(file_path):
    """Read imatrix file with multiple weights."""
    weights = {}
    with open(file_path, "rb") as f:
        try:
            n_entries = struct.unpack('<i', f.read(4))[0]
            for _ in range(n_entries):
                name_len = struct.unpack('<i', f.read(4))[0]
                name = f.read(name_len).decode('utf-8')
                n_call = struct.unpack('<i', f.read(4))[0]
                n_values = struct.unpack('<i', f.read(4))[0]
                values = np.frombuffer(f.read(n_values * 4), dtype=np.float32)
                weights[name] = {
                    'n_call': n_call,
                    'values': values,
                }
            last_call = struct.unpack('<i', f.read(4))[0]
            input_filename_len = struct.unpack('<i', f.read(4))[0]
            input_filename = f.read(input_filename_len).decode('utf-8')
        except struct.error as e:
            print(f"Error reading imatrix file: {e}")
            return None
    return weights

def normalize_matrix(matrix):
    """Normalize matrix values to the range [0, 1]."""
    min_val = np.min(matrix)
    max_val = np.max(matrix)
    if max_val - min_val == 0:
        return np.zeros_like(matrix)
    return (matrix - min_val) / (max_val - min_val)

def determine_quant_tier(base_quant: str, mad: float, corr: float) -> str:
    """Select a quantization type based on sensitivity."""
    try:
        base_idx = quant_levels.index(base_quant)
    except ValueError:
        base_idx = quant_levels.index("Q4_K_M")  # fallback

    # Adjust quant level based on sensitivity
    if mad > 0.01 or corr < 0.80:
        bump = 3
    elif mad > 0.005 or corr < 0.90:
        bump = 2
    elif mad > 0.002 or corr < 0.95:
        bump = 1
    else:
        bump = 0

    new_idx = min(base_idx + bump, len(quant_levels) - 1)
    return quant_levels[new_idx]

def compare_imatrix(file1, file2, mad_threshold=0.002, corr_threshold=0.95, base_quant="Q4_K_M"):
    """Compare two imatrix files and suggest quant types per tensor."""
    weights1 = read_imatrix(file1)
    weights2 = read_imatrix(file2)

    if weights1 is None or weights2 is None:
        print("Error reading imatrix files.")
        return

    if weights1.keys() != weights2.keys():
        print("The imatrix files have different weights.")
        return

    total_mad, total_msd, total_corr = 0.0, 0.0, 0.0
    total_weights = 0
    sensitive_layers = []
    quant_suggestions = []

    for name in weights1:
        imatrix1 = weights1[name]['values']
        imatrix2 = weights2[name]['values']

        if len(imatrix1) != len(imatrix2):
            print(f"The weight tensors for '{name}' have different sizes.")
            continue

        imatrix1_norm = normalize_matrix(imatrix1)
        imatrix2_norm = normalize_matrix(imatrix2)
        diff = imatrix1_norm - imatrix2_norm

        mad = np.mean(np.abs(diff))
        msd = np.mean(diff ** 2)
        corr = np.corrcoef(imatrix1_norm, imatrix2_norm)[0, 1]

        print(f"\nWeight: {name}")
        print(f"  MAD: {mad:.6f}")
        print(f"  MSD: {msd:.6f}")
        print(f"  Corr: {corr:.6f}")

        if mad > mad_threshold or corr < corr_threshold:
            print("  -> Sensitive layer")
            suggested_quant = determine_quant_tier(base_quant, mad, corr)
            quant_suggestions.append((name, suggested_quant))
            sensitive_layers.append({
                'name': name, 'mad': mad, 'msd': msd, 'corr': corr, 'quant': suggested_quant
            })

        total_mad += mad
        total_msd += msd
        total_corr += corr
        total_weights += 1

        plt.figure(figsize=(10, 6))
        plt.plot(imatrix1_norm, label="File 1 (Normalized)")
        plt.plot(imatrix2_norm, label="File 2 (Normalized)")
        plt.plot(diff, label="Difference")
        plt.title(f"Comparison of {name}")
        plt.xlabel("Index")
        plt.ylabel("Value")
        plt.legend()
        plt.savefig(f"{name}_comparison.png")
        plt.close()

    print("\n=== Suggested --tensor-type arguments ===")
    for name, quant in quant_suggestions:
        print(f"--tensor-type {name}={quant}")

    print("\n=== Summary ===")
    print(f"Avg MAD: {total_mad / total_weights:.6f}")
    print(f"Avg MSD: {total_msd / total_weights:.6f}")
    print(f"Avg Corr: {total_corr / total_weights:.6f}")

# Example usage
imatrix_file1 = "../models/imatrix-files/Qwen3-0.6B-abliterated.imatrix"
imatrix_file2 = "../models/imatrix-files/test.imatrix"
compare_imatrix(imatrix_file1, imatrix_file2, base_quant="Q4_K_M")

