#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import platform
import argparse
from pathlib import Path

# Shared constraints keep both installers on the tested conversion stack.
PROJECT_DIR = Path(__file__).resolve().parent
CONSTRAINTS = PROJECT_DIR / "constraints-converter.txt"
CORE_REQUIREMENTS = PROJECT_DIR / "requirements-converter.txt"

# Optional audio/application dependencies for the full installer.
common_requirements = [
    "flask", "flask-cors", "librosa", "soundfile", "phonemizer", "munch",
    "werkzeug", "num2words", "dateparser", "inflect", "ftfy",
]

def verify_llama_dir(explicit_dir=None):
    from dotenv import load_dotenv

    load_dotenv(PROJECT_DIR / ".env")
    llama_dir = explicit_dir or os.getenv("LLAMA_CPP_DIR")
    if not llama_dir:
        print("[WARN] LLAMA_CPP_DIR not set (.env). You can set it to your llama.cpp path.")
        return None
    p = Path(llama_dir)
    conv = p / "convert_hf_to_gguf.py"
    if not conv.exists():
        raise FileNotFoundError(f"convert_hf_to_gguf.py not found in {p}")
    else:
        print(f"[INFO] Found llama.cpp converter at: {conv}")
    return str(p)


def run(cmd: str) -> None:
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to run command: {cmd}\nError: {e}")
        raise

def pip_install(pkg: str, extra_args=None, retries: int = 1) -> None:
    cmd = [sys.executable, "-m", "pip", "install", "--constraint", str(CONSTRAINTS), pkg]
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
    parser = argparse.ArgumentParser(description="Install the tested GGUF conversion stack")
    parser.add_argument("--mode", choices=("cpu", "gpu"))
    parser.add_argument("--llama-dir", help="Local llama.cpp checkout")
    parser.add_argument("--core-only", action="store_true", help="Skip optional audio/ONNX packages and system dependencies")
    args = parser.parse_args()

    # Bootstrap dotenv before inspecting .env in a fresh virtual environment.
    pip_install("python-dotenv")
    verify_llama_dir(args.llama_dir)
    mode = detect_mode(default="cpu")

    # Install PyTorch first so dependency resolution cannot select a CUDA build
    # in CPU mode. The shared constraint also applies to every later pip call.
    if mode == "cpu":
        pip_install("torch==2.11.0+cpu", ["--index-url", "https://download.pytorch.org/whl/cpu"])
    else:
        pip_install("torch==2.11.0")

    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--upgrade",
        "--constraint", str(CONSTRAINTS), "--requirement", str(CORE_REQUIREMENTS),
    ])

    if not args.core_only:
        install_system_dependencies()
        for req in common_requirements:
            pip_install(req)
        pip_install("onnxruntime" if mode == "cpu" else "onnxruntime-gpu")

    subprocess.check_call([sys.executable, "-m", "pip", "check"])
    print("\nInstallation complete!")

if __name__ == "__main__":
    main()
