
---

## GGUFModelBuilder

This codebase provides a **machine learning model conversion and management pipeline** designed to:

* Automate conversion of Hugging Face models to GGUF format (with quantization and metadata)
* Manage a Redis-based catalog of models and their metadata
* Support batch and single-model processing
* Detect new models via GitHub commit analysis
* Provide a web interface for catalog editing and search

---

# Main Components

## 1. Model Conversion Pipeline (`model_converter.py` and helpers)

* Downloads models from Hugging Face using the API
* Converts models to **GGUF format (BF16)** via `llama.cpp` scripts
* Quantizes models into various formats:

  * `Q4_K`, `IQ1_S`, `IQ3_XS`, etc.
* Adds metadata to GGUF files for compatibility and traceability
* Uploads quantized models to Hugging Face Hub (with chunking)
* Cleans up disk/cache for efficient storage
* Tracks model status in Redis:

  * Conversion attempts, successes, errors, quantizations
* Detects **Mixture-of-Experts (MoE)** models and applies special handling

## 2. Catalog Management

* Redis-based catalog storing:

  * Model metadata
  * Conversion/quantization status
* Batch support via JSON lists
* **Web UI** (`gguf-catalog-editor/app.py`) built with Flask for:

  * Searching, editing, adding, deleting
  * Import/export
  * Restore from backup

## 3. Automation & Monitoring

* `auto_build_new_models.py`:
  Watches `llama.cpp` GitHub repo for commits, analyzes them via local LLM, and updates the catalog with new models
* `build_llama.py`:
  Automates building and patching of `llama.cpp` binaries

## 4. Supporting Scripts

* `download_convert.py`: Download + convert to BF16 GGUF
* `make_files.py`: Quantize, chunk, upload, update README
* `upload-files.py`: Upload GGUF files to Hugging Face and clean up
* `add_metadata_gguf.py`: Insert/override metadata in GGUF files
* `update_readme.py`: Populate README with quantization info
* `tensor_list_builder.py`: Suggest quant strategies per tensor/layer

### Quant selection policy (updated)

* **Effective bpw map (used for sorting/filtering):** IQ1_S≈1.6, IQ1_M≈1.75; IQ2_XXS→M≈2.1–2.6; Q2_K*≈2.6; IQ3_XXS→M≈3.1–3.4; Q3_K*≈3.3; IQ4_NL≈3.8, IQ4_XS≈4.5; Q4*≈4.0–4.5; Q5*≈5.0–5.5; Q6_K≈6.6; Q8_0=8; F16/BF16=16.
* **Family split with rollover:** IQ targets climb the IQ ladder and, after topping out, roll into stronger K quants; K targets stay in K.
* **Rules:** `quant_rules.json` has separate IQ-only and K-only entries for mid-bit rules so bumps stay in-family unless IQ needs to roll up into K.
* **Bit budget filtering:** `make_files.py` uses size-aware thresholds: <4B params start around ~3 bpw (skip IQ1/2 + Q2); 4–10B allow ~2.x bpw; >10B allow the full range including IQ1_S/M. If the Redis catalog has `expert_param_size` or `no_experts`, the per-expert size is used for this decision to keep MoE experts off ultra-low bpw.

---

# How It Works (Typical Flow)

```mermaid
flowchart TD
    A["Select Model"] --> B["Download from HF"]
    B --> C["Convert to BF16 GGUF"]
    C --> D["Quantize to Q4_K / Q6_K / etc."]
    D --> E["Add Metadata & Update README"]
    E --> F["Upload to HF (chunk if large)"]
    F --> G["Update Redis Catalog"]
```

# Technologies Used

* **Python** – core language
* **llama.cpp** – model conversion and quantization
* **Hugging Face Hub** – model hosting and API
* **Redis** – catalog database
* **Flask** – web UI
* **dotenv** – configuration
* **Subprocess, threading, multiprocessing** – for tooling and parallelism

---

# Summary

* End-to-end pipeline to **convert, quantize, and upload** LLMs in GGUF format
* Redis catalog tracks **model status and metadata**
* **Web UI** for catalog browsing and editing
* Monitors GitHub to auto-detect and process new models
* Modular and scalable: Each step is handled by a distinct script/function

---

| Component | Link |
|-----------|------|
| Model Converter | [GGUF Model Converter](https://github.com/Mungert69/GGUFModelBuilder/wiki/Model-Converter) |
| Catalog Editor | [GGUF Model Catalog Editor](https://github.com/Mungert69/GGUFModelBuilder/wiki/GGUF-Model-Catalog-Editor) |


## 🌐 Community

[![Discord](https://img.shields.io/badge/Discord-Join_Server-5865F2?logo=discord)](https://discord.gg/rne7YaK3)


## 🤝 Sponsors

<a href="https://readyforquantum.com" target="_blank">
  <img src="https://readyforquantum.com/logo.png" alt="ReadyForQuantum" width="200">
</a>


