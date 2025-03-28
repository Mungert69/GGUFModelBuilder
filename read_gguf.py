import sys
import gguf

def read_gguf_metadata(file_path):
    reader = gguf.GGUFReader(file_path)

    print("\n🔍 GGUF Metadata:")
    for key, value in reader.metadata.items():
        print(f"{key}: {value}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 read_gguf.py <gguf_file>")
        sys.exit(1)

    gguf_file = sys.argv[1]
    read_gguf_metadata(gguf_file)

