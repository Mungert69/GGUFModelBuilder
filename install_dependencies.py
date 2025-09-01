#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import platform
import argparse
import importlib.util
import sysconfig
from dotenv import load_dotenv
from pathlib import Path

# ---- requirements (no stdlib modules here) ----
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
    "num2words",
    "dateparser",
    "inflect",
    "ftfy",
    "sentencepiece",
]
# add at top with others:
import os
from dotenv import load_dotenv
from pathlib import Path

def verify_llama_dir():
    load_dotenv()
    llama_dir = os.getenv("LLAMA_CPP_DIR")
    if not llama_dir:
        print("[WARN] LLAMA_CPP_DIR not set (.env). You can set it to your llama.cpp path.")
        return None
    p = Path(llama_dir)
    conv = p / "convert_hf_to_gguf.py"
    if not conv.exists():
        print(f"[WARN] convert_hf_to_gguf.py not found in {p}. Check LLAMA_CPP_DIR.")
    else:
        print(f"[INFO] Found llama.cpp converter at: {conv}")
    return str(p)


def run(cmd: str) -> None:
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to run command: {cmd}\nError: {e}")
        raise

def is_stdlib(module_name: str) -> bool:
    """
    Defensive guard: if someone accidentally puts a stdlib module name
    into the requirements list, skip pip-installing it.
    """
    spec = importlib.util.find_spec(module_name)
    if not spec or not spec.origin:
        return False
    stdlib_path = sysconfig.get_paths().get("stdlib") or ""
    return spec.origin.startswith(stdlib_path)

def pip_install(pkg: str, extra_args=None, retries: int = 1) -> None:
    cmd = [sys.executable, "-m", "pip", "install", pkg]
    if extra_args:
        cmd.extend(extra_args)
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        if retries > 0:
            print(f"[WARN] pip install failed for {pkg}. Retrying once...")
            subprocess.check_call(cmd)
        else:
            print(f"Failed to install {pkg}: {e}")
            raise

def install_system_dependencies() -> None:
    print("\nInstalling system dependencies (audio/libs)...")
    os_type = platform.system()
    if os_type == "Linux":
        print("Detected Linux. Installing espeak, libsndfile1, ffmpeg (if missing)...")
        try:
            run("sudo apt-get update && sudo apt-get install -y espeak libsndfile1 ffmpeg")
        except Exception:
            print("[WARN] Skipping apt install (not Debian/Ubuntu or no sudo).")
    elif os_type == "Darwin":
        print("Detected macOS. If needed, install via Homebrew:")
        print("  brew install espeak libsndfile ffmpeg")
    elif os_type == "Windows":
        print("Detected Windows. Ensure espeak and libsndfile are installed if required.")
    else:
        print(f"Unsupported OS: {os_type}. Skipping system dependency installation.")

def detect_mode(default: str = "cpu") -> str:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=("cpu", "gpu"), help="Override install mode.")
    args, _ = parser.parse_known_args()

    if args.mode:
        mode = args.mode
    else:
        env_mode = os.environ.get("INSTALL_MODE", "").strip().lower()
        if env_mode in ("cpu", "gpu"):
            mode = env_mode
        else:
            has_gpu = shutil.which("nvidia-smi") or shutil.which("nvcc")
            mode = "gpu" if has_gpu else default

    print(f"\nInstallation mode: {mode.upper()}")
    return mode

def main() -> None:
    print("Detecting operating system...")
    os_type = platform.system()
    print(f"Operating system detected: {os_type}")

    llama_dir = verify_llama_dir()

    install_system_dependencies()

    mode = detect_mode(default="cpu")

    # Install common packages first
    print("\nInstalling common Python requirements...")
    for req in common_requirements:
        # Guard against accidental stdlib names
        mod_name = req.split("==")[0].split("[")[0].replace("-", "_")
        if is_stdlib(mod_name):
            print(f"[INFO] Skipping stdlib module '{req}'.")
            continue
        print(f"Installing {req}...")
        pip_install(req)

    # Torch + ONNX stacks
    if mode == "cpu":
        print("\nInstalling torch (CPU-only wheels)...")
        pip_install("torch", ["--index-url", "https://download.pytorch.org/whl/cpu"])
        print("Installing onnxruntime (CPU-only)...")
        pip_install("onnxruntime")
    else:
        print("\nInstalling torch (GPU/CUDA, default index)...")
        pip_install("torch")
        print("Installing onnxruntime-gpu...")
        pip_install("onnxruntime-gpu")

    print("\nInstallation complete!")

if __name__ == "__main__":
    main()

