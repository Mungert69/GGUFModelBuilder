import numpy as np
import struct
import matplotlib.pyplot as plt

def read_imatrix(file_path):
    """Read imatrix file with multiple weights."""
    weights = {}
    with open(file_path, "rb") as f:
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
    
    return weights

def normalize_matrix(matrix):
    """Normalize matrix values to the range [0, 1]."""
    min_val = np.min(matrix)
    max_val = np.max(matrix)
    return (matrix - min_val) / (max_val - min_val)

def compare_imatrix(file1, file2):
    """Compare two imatrix files."""
    # Read the imatrix files
    weights1 = read_imatrix(file1)
    weights2 = read_imatrix(file2)

    # Ensure the files have the same weights
    if weights1.keys() != weights2.keys():
        raise ValueError("The imatrix files have different weights.")

    # Initialize grand totals
    total_nans_file1 = 0
    total_nans_file2 = 0
    total_infs_file1 = 0
    total_infs_file2 = 0
    total_mad = 0.0
    total_msd = 0.0
    total_corr = 0.0
    total_weights = 0

    # Compare each weight tensor
    for name in weights1:
        imatrix1 = weights1[name]['values']
        imatrix2 = weights2[name]['values']

        # Ensure the weight tensors have the same size
        if len(imatrix1) != len(imatrix2):
            raise ValueError(f"The weight tensors for '{name}' have different sizes.")

        # Check for NaNs/Infs
        nans_file1 = np.isnan(imatrix1).sum()
        nans_file2 = np.isnan(imatrix2).sum()
        infs_file1 = np.isinf(imatrix1).sum()
        infs_file2 = np.isinf(imatrix2).sum()

        # Print NaNs/Infs only if they exist
        if nans_file1 > 0 or nans_file2 > 0 or infs_file1 > 0 or infs_file2 > 0:
            print(f"\nWeight: {name}")
            if nans_file1 > 0:
                print(f"NaNs in file1: {nans_file1}")
            if nans_file2 > 0:
                print(f"NaNs in file2: {nans_file2}")
            if infs_file1 > 0:
                print(f"Infs in file1: {infs_file1}")
            if infs_file2 > 0:
                print(f"Infs in file2: {infs_file2}")

        # Replace NaNs/Infs with 0 for comparison
        imatrix1 = np.nan_to_num(imatrix1, nan=0.0, posinf=0.0, neginf=0.0)
        imatrix2 = np.nan_to_num(imatrix2, nan=0.0, posinf=0.0, neginf=0.0)

        # Normalize the matrices
        imatrix1_norm = normalize_matrix(imatrix1)
        imatrix2_norm = normalize_matrix(imatrix2)

        # Compute differences using float64 to avoid overflow
        diff = imatrix1_norm - imatrix2_norm

        # Calculate metrics
        mad = np.mean(np.abs(diff))
        msd = np.mean(diff**2)
        corr = np.corrcoef(imatrix1_norm, imatrix2_norm)[0, 1]

        # Print statistics
        print(f"\nWeight: {name}")
        print(f"Mean Absolute Difference: {mad:.6f}")
        print(f"Max Absolute Difference: {np.max(np.abs(diff)):.6f}")
        print(f"Mean Squared Difference: {msd:.6f}")
        print(f"Correlation: {corr:.6f}")

        # Update grand totals
        total_nans_file1 += nans_file1
        total_nans_file2 += nans_file2
        total_infs_file1 += infs_file1
        total_infs_file2 += infs_file2
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
        plt.savefig(f"{name}_comparison.png")  # Save the plot to a file
        plt.close()  # Close the figure to free memory

    # Print grand totals
    print("\n=== Grand Totals ===")
    print(f"Total NaNs in file1: {total_nans_file1}")
    print(f"Total NaNs in file2: {total_nans_file2}")
    print(f"Total Infs in file1: {total_infs_file1}")
    print(f"Total Infs in file2: {total_infs_file2}")
    print(f"Average Mean Absolute Difference: {total_mad / total_weights:.6f}")
    print(f"Average Mean Squared Difference: {total_msd / total_weights:.6f}")
    print(f"Average Correlation: {total_corr / total_weights:.6f}")

# Paths to the imatrix files
imatrix_file1 = "./llama.cpp/imatrix.dat.q8_0"
imatrix_file2 = "./llama.cpp/imatrix.dat.at_10"

# Compare the imatrix files
compare_imatrix(imatrix_file1, imatrix_file2)
