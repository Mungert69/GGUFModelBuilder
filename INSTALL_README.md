
# GGUFModelBuilder – Installation Guide

This project provides an automated installer that sets up everything you need:
- A Python virtual environment (`venv`)
- Required system dependencies (build tools, audio libs, BLAS)
- Python dependencies (`huggingface_hub`, `redis`, `gguf`, etc.)
- [`llama-cpp-python`](https://github.com/abetlen/llama-cpp-python) built for **CPU** or **CUDA**
- Additional runtime libraries via `install_dependencies.py`

---

## Quick Start

```bash
# Clone repo
git clone https://github.com/your-org/GGUFModelBuilder.git
cd GGUFModelBuilder

# Make installer executable
chmod +x install

# Run installer (CPU build, default)
./install

# Or explicitly request CUDA build
./install cuda
````

When complete, your Python environment will be located in:

```
./venv ```

Activate it with:

```bash
source venv/bin/activate
```

---

## Build Modes

The first argument to `./install` controls how `llama-cpp-python` is built:

* **CPU build** (default):

  ```bash
  ./install
  # or
  ./install cpu
  ```

* **CUDA build** (requires NVIDIA GPU + CUDA toolkit):

  ```bash
  ./install cuda
  ```

This mode is passed through as `INSTALL_MODE` to `install_dependencies.py`, ensuring **Torch** and **ONNXRuntime** are installed with matching CPU/GPU support.

---

## What the Installer Does

1. **System Dependencies**

   * Installs required build tools (`gcc`, `g++`, `cmake`, `ninja`, `pkg-config`)
   * Installs audio & BLAS libs (`espeak`, `libsndfile1`, `ffmpeg`, `libopenblas-dev`)

2. **Python Virtual Environment**

   * Creates `./venv` with your system’s `python3`
   * Upgrades `pip`, `setuptools`, `wheel`, `cmake`, and `scikit-build-core`

3. **Python Packages**

   * Installs base deps:
     `python-dotenv huggingface_hub gguf redis hf_xet`
   * Builds or installs a wheel for **llama-cpp-python** (CPU or CUDA mode)

4. **Application Dependencies**

   * Runs `install_dependencies.py`, which installs:

     * Common libs (`flask`, `transformers`, `librosa`, etc.)
     * **Torch** + **ONNXRuntime** with CPU or GPU support

---

## Switching Between CPU and GPU

If you installed in CPU mode but later want GPU, just re-run:

```bash
./install cuda
```

This will rebuild `llama-cpp-python` with CUDA and reinstall the GPU variants of Torch/ONNXRuntime.

---

## Troubleshooting

* **Missing venv support**
  If you see errors about `venv`, install it via apt:

  ```bash
  sudo apt install python3-venv python3-dev
  ```

* **Build failures for `llama-cpp-python`**
  Ensure build tools are installed:

  ```bash
  sudo apt install build-essential cmake ninja-build pkg-config libopenblas-dev
  ```

* **Torch installation issues**
  If CUDA isn’t detected but you expected GPU support, check your NVIDIA drivers and `nvidia-smi`.

---

## Manual Control

You can also run `install_dependencies.py` directly:

```bash
# CPU
INSTALL_MODE=cpu python install_dependencies.py

# GPU
INSTALL_MODE=gpu python install_dependencies.py
```

Or override via CLI:

```bash
python install_dependencies.py --mode gpu
```

---

## Next Steps

After installation:

```bash
source venv/bin/activate
```

You’re ready to start using GGUFModelBuilder!



