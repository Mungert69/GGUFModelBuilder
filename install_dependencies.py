import subprocess
import sys
import platform

# Define the common requirements
common_requirements = [
    "flask",
    "flask-cors",
    "transformers",
    "librosa",
    "numpy",
    "soundfile",
    "huggingface_hub",
    "phonemizer",
    "munch",
    "werkzeug",
    "tempfile",
    "num2words",
    "dateparser",
    "hashlib",
    "inflect",
    "ftfy"
]

# Function to run shell commands
def run_command(command):
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to run command: {command}\nError: {e}")

# Function to install Python packages
def install_package(package, extra_args=None):
    try:
        command = [sys.executable, "-m", "pip", "install", package]
        if extra_args:
            command.extend(extra_args)
        subprocess.check_call(command)
    except subprocess.CalledProcessError as e:
        print(f"Failed to install {package}: {e}")

# Install system dependencies
def install_system_dependencies():
    print("\nInstalling system dependencies...")
    os_type = platform.system()
    if os_type == "Linux":
        print("Detected Linux. Installing espeak and other dependencies...")
        run_command("sudo apt-get update && sudo apt-get install -y espeak libsndfile1")
    elif os_type == "Darwin":
        print("Detected macOS. Please install espeak manually using Homebrew.")
        print("Run: brew install espeak")
    elif os_type == "Windows":
        print("Detected Windows. Ensure espeak is installed manually if required.")
    else:
        print(f"Unsupported OS: {os_type}. Skipping system dependencies installation.")

# Main installation logic
def main():
    print("Detecting operating system...")
    os_type = platform.system()
    print(f"Operating system detected: {os_type}")

    install_system_dependencies()

    print("\nSelect installation mode:")
    print("1. CPU (no GPU dependencies)")
    print("2. GPU (requires CUDA-compatible hardware and drivers)")

    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        print("\nInstalling for CPU...")
        for req in common_requirements:
            print(f"Installing {req}...")
            install_package(req)
        print("Installing torch (CPU-only)...")
        install_package("torch", ["--index-url", "https://download.pytorch.org/whl/cpu"])
        print("Installing onnxruntime (CPU-only)...")
        install_package("onnxruntime")
    elif choice == "2":
        print("\nInstalling for GPU...")
        for req in common_requirements:
            print(f"Installing {req}...")
            install_package(req)
        print("Installing torch (GPU)...")
        install_package("torch")
        print("Installing onnxruntime-gpu...")
        install_package("onnxruntime-gpu")
    else:
        print("\nInvalid choice. Exiting.")
        sys.exit(1)

    print("\nInstallation complete!")

if __name__ == "__main__":
    main()

