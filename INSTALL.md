# Installing the converter

The verified setup uses Python 3.13 on Linux with CPU PyTorch. From this directory:

```bash
./install --llama-dir /home/mahadeva/code/models/llama.cpp --mode cpu --yes
```

Both `install` and `install_dependencies.py` use `requirements-converter.txt`
and `constraints-converter.txt`. The constraints pin the tested conversion
packages, including Transformers 5.22.2, NumPy 2.2.6, PyTorch 2.11.0,
protobuf 4.25.9, and GGUF 0.19.0. CPU mode selects PyTorch 2.11.0+cpu.
Do not subsequently install the checkout's requirements files: their old
Transformers pin would undo LFM3 tokenizer support. The checkout is validated
but its requirements and source are not modified.

For an existing activated virtual environment:

```bash
python install_dependencies.py --core-only --mode cpu --llama-dir /path/to/llama.cpp
```

Omit `--core-only` to include the existing optional audio/application dependencies,
system libraries, and ONNX runtime. `--mode gpu` selects the PyPI PyTorch build;
GPU installation has not been validated on this machine.

Both installers run `pip check` at completion. These are conversion-stack
constraints, not a complete environment lock: optional packages, transitive
packages, and build tools can still resolve to newer compatible versions.
When updating the pins, check dependency resolution and export the LFM3
vocabulary with llama.cpp before running a full model conversion.
