import numpy as np
import struct
import matplotlib.pyplot as plt

def read_imatrix(file_path):
    """Read imatrix file with multiple weights."""
    weights = {}
    with open(file_path, "rb") as f:
        try:
            # Read number of entries (4 bytes)
            n_entries = struct.unpack('<i', f.read(4))[0]
            
            for _ in range(n_entries):
                # Read name length (4 bytes)
                name_len = struct.unpack('<i', f.read(4))[0]
                
                # Read name (variable length, UTF-8 encoded)
                name = f.read(name_len).decode('utf-8')
                
                # Read number of calls (4 bytes)
                n_call = struct.unpack('<i', f.read(4))[0]
                
                # Read number of values (4 bytes)
                n_values = struct.unpack('<i', f.read(4))[0]
                
                # Read values (n_values * float32)
                values = np.frombuffer(f.read(n_values * 4), dtype=np.float32)
                
                # Store the weight tensor
                weights[name] = {
                    'n_call': n_call,
                    'values': values,
                }
                
                print(f"Read weight: {name}")
                print(f"  Number of calls: {n_call}")
                print(f"  Number of values: {n_values}")
                print(f"  Sample data (first 10 values): {values[:10]}")
            
            # Read last call (4 bytes)
            last_call = struct.unpack('<i', f.read(4))[0]
            print(f"Last call: {last_call}")
            
            # Read input filename length (4 bytes)
            input_filename_len = struct.unpack('<i', f.read(4))[0]
            
            # Read input filename (variable length, UTF-8 encoded)
            input_filename = f.read(input_filename_len).decode('utf-8')
            print(f"Input filename: {input_filename}")
        
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

def compare_imatrix(file1, file2, mad_threshold=0.002, corr_threshold=0.95):
    """Compare two imatrix files and identify sensitive layers."""
    # Read the imatrix files
    weights1 = read_imatrix(file1)
    weights2 = read_imatrix(file2)

    if weights1 is None or weights2 is None:
        print("Error reading imatrix files.")
        return

    # Ensure the files have the same weights
    if weights1.keys() != weights2.keys():
        print("The imatrix files have different weights.")
        return

    # Initialize grand totals
    total_mad = 0.0
    total_msd = 0.0
    total_corr = 0.0
    total_weights = 0
    sensitive_layers = []

    # Compare each weight tensor
    for name in weights1:
        imatrix1 = weights1[name]['values']
        imatrix2 = weights2[name]['values']

        # Ensure the weight tensors have the same size
        if len(imatrix1) != len(imatrix2):
            print(f"The weight tensors for '{name}' have different sizes.")
            continue

        # Normalize the matrices
        imatrix1_norm = normalize_matrix(imatrix1)
        imatrix2_norm = normalize_matrix(imatrix2)

        # Compute differences
        diff = imatrix1_norm - imatrix2_norm

        # Calculate metrics
        mad = np.mean(np.abs(diff))
        msd = np.mean(diff**2)
        corr = np.corrcoef(imatrix1_norm, imatrix2_norm)[0, 1]

        # Print statistics
        print(f"\nWeight: {name}")
        print(f"Mean Absolute Difference: {mad:.6f}")
        print(f"Mean Squared Difference: {msd:.6f}")
        print(f"Correlation: {corr:.6f}")

        # Check if the layer is sensitive
        if mad > mad_threshold or corr < corr_threshold:
            print("-> Sensitive layer detected. Consider allocating more bits.")
            sensitive_layers.append({
                'name': name,
                'mad': mad,
                'msd': msd,
                'corr': corr
            })

        # Update grand totals
        total_mad += mad
        total_msd += msd
        total_corr += corr
        total_weights += 1

        # Plot the differences
        plt.figure(figsize=(10, 6))
        plt.plot(imatrix1_norm, label="File 1 (Normalized)")
        plt.plot(imatrix2_norm, label="File 2 (Normalized)")
        plt.plot(diff, label="Difference")
        plt.title(f"Comparison of {name} (Normalized)")
        plt.xlabel("Index")
        plt.ylabel("Value")
        plt.legend()
        plt.savefig(f"{name}_comparison.png")
        plt.close()

    # Print grand totals
    print("\n=== Grand Totals ===")
    print(f"Average Mean Absolute Difference: {total_mad / total_weights:.6f}")
    print(f"Average Mean Squared Difference: {total_msd / total_weights:.6f}")
    print(f"Average Correlation: {total_corr / total_weights:.6f}")

    # Output sensitive layers
    if sensitive_layers:
        print("\n=== Sensitive Layers ===")
        for layer in sensitive_layers:
            print(f"Layer: {layer['name']}")
            print(f"  MAD: {layer['mad']:.6f}")
            print(f"  MSD: {layer['msd']:.6f}")
            print(f"  Correlation: {layer['corr']:.6f}")
    else:
        print("\nNo sensitive layers detected.")

# Paths to the imatrix files
imatrix_file1 = "../models/imatrix-files/Qwen3-0.6B-abliterated.imatrix"
imatrix_file2 = "../models/imatrix-files/test.imatrix"

# Compare the imatrix files
compare_imatrix(imatrix_file1, imatrix_file2)

