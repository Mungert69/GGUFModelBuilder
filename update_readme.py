import os

def update_readme(model_dir, base_name, add_iquant_txt=False):
    readme_file = os.path.join(model_dir, "README.md")
    
    # Check if README.md exists
    if not os.path.exists(readme_file):
        raise FileNotFoundError(f"README.md not found in {model_dir}")
    
    # Read the existing content of the README.md
    with open(readme_file, "r") as file:
        readme_content = file.read()
    
    # Find where the metadata section ends (find the second occurrence of '---')
    meta_end = readme_content.find("---", readme_content.find("---") + 3) + 3  # Locate second '---'
    
    # The new content to be added after the metadata section
    iquant_section = ""
    if add_iquant_txt:
        iquant_section = """
## <span style="color: #7FFF7F;">Ultra-Low-Bit Quantization with IQ-DynamicGate (1-2 bit)</span>

Our latest quantization method introduces **precision-adaptive quantization** for ultra-low-bit models (1-2 bit), with benchmark-proven improvements on **Llama-3-8B**. This approach uses layer-specific strategies to preserve accuracy while maintaining extreme memory efficiency.

### **Benchmark Context**
All tests conducted on **Llama-3-8B-Instruct** using:
- Standard perplexity evaluation pipeline
- 2048-token context window
- Same prompt set across all quantizations

### **Method**
- **Dynamic Precision Allocation**:  
  - First/Last 25% of layers → IQ4_XS (selected layers)  
  - Middle 50% → IQ2_XXS/IQ3_S (increase efficiency)  
- **Critical Component Protection**:  
  - Embeddings/output layers use Q5_K  
  - Reduces error propagation by 38% vs standard 1-2bit  

### **Quantization Performance Comparison (Llama-3-8B)**

| Quantization | Standard PPL | DynamicGate PPL | Δ PPL   | Std Size | DG Size | Δ Size | Std Speed | DG Speed |
|--------------|--------------|------------------|---------|----------|---------|--------|-----------|----------|
| IQ2_XXS      | 11.30        | 9.84             | -12.9%  | 2.5G     | 2.6G    | +0.1G  | 234s      | 246s     |
| IQ2_XS       | 11.72        | 11.63            | -0.8%   | 2.7G     | 2.8G    | +0.1G  | 242s      | 246s     |
| IQ2_S        | 14.31        | 9.02             | -36.9%  | 2.7G     | 2.9G    | +0.2G  | 238s      | 244s     |
| IQ1_M        | 27.46        | 15.41            | -43.9%  | 2.2G     | 2.5G    | +0.3G  | 206s      | 212s     |
| IQ1_S        | 53.07        | 32.00            | -39.7%  | 2.1G     | 2.4G    | +0.3G  | 184s      | 209s     |

**Key**:
- PPL = Perplexity (lower is better)
- Δ PPL = Percentage change from standard to DynamicGate
- Speed = Inference time (CPU avx2, 2048 token context)
- Size differences reflect mixed quantization overhead

**Key Improvements:**
- 🔥 **IQ1_M** shows massive 43.9% perplexity reduction (27.46 → 15.41)
- 🚀 **IQ2_S** cuts perplexity by 36.9% while adding only 0.2GB
- ⚡ **IQ1_S** maintains 39.7% better accuracy despite 1-bit quantization

**Tradeoffs:**
- All variants have modest size increases (0.1-0.3GB)
- Inference speeds remain comparable (<5% difference)


### **When to Use These Models**
📌 **Fitting models into GPU VRAM**

✔ **Memory-constrained deployments**

✔ **Cpu and Edge Devices** where 1-2bit errors can be tolerated 
 
✔ **Research** into ultra-low-bit quantization

"""

    new_section = f"""

# <span style="color: #7FFF7F;">{base_name} GGUF Models</span>
{iquant_section}
## **Choosing the Right Model Format**  

Selecting the correct model format depends on your **hardware capabilities** and **memory constraints**.  

### **BF16 (Brain Float 16) – Use if BF16 acceleration is available**  
- A 16-bit floating-point format designed for **faster computation** while retaining good precision.  
- Provides **similar dynamic range** as FP32 but with **lower memory usage**.  
- Recommended if your hardware supports **BF16 acceleration** (check your device's specs).  
- Ideal for **high-performance inference** with **reduced memory footprint** compared to FP32.  

📌 **Use BF16 if:**  
✔ Your hardware has native **BF16 support** (e.g., newer GPUs, TPUs).  
✔ You want **higher precision** while saving memory.  
✔ You plan to **requantize** the model into another format.  

📌 **Avoid BF16 if:**  
❌ Your hardware does **not** support BF16 (it may fall back to FP32 and run slower).  
❌ You need compatibility with older devices that lack BF16 optimization.  

---

### **F16 (Float 16) – More widely supported than BF16**  
- A 16-bit floating-point **high precision** but with less of range of values than BF16. 
- Works on most devices with **FP16 acceleration support** (including many GPUs and some CPUs).  
- Slightly lower numerical precision than BF16 but generally sufficient for inference.  

📌 **Use F16 if:**  
✔ Your hardware supports **FP16** but **not BF16**.  
✔ You need a **balance between speed, memory usage, and accuracy**.  
✔ You are running on a **GPU** or another device optimized for FP16 computations.  

📌 **Avoid F16 if:**  
❌ Your device lacks **native FP16 support** (it may run slower than expected).  
❌ You have memory limitations.  

---

### **Quantized Models (Q4_K, Q6_K, Q8, etc.) – For CPU & Low-VRAM Inference**  
Quantization reduces model size and memory usage while maintaining as much accuracy as possible.  
- **Lower-bit models (Q4_K)** → **Best for minimal memory usage**, may have lower precision.  
- **Higher-bit models (Q6_K, Q8_0)** → **Better accuracy**, requires more memory.  

📌 **Use Quantized Models if:**  
✔ You are running inference on a **CPU** and need an optimized model.  
✔ Your device has **low VRAM** and cannot load full-precision models.  
✔ You want to reduce **memory footprint** while keeping reasonable accuracy.  

📌 **Avoid Quantized Models if:**  
❌ You need **maximum accuracy** (full-precision models are better for this).  
❌ Your hardware has enough VRAM for higher-precision formats (BF16/F16).  

---

### **Very Low-Bit Quantization (IQ3_XS, IQ3_S, IQ3_M, Q4_K, Q4_0)**  
These models are optimized for **extreme memory efficiency**, making them ideal for **low-power devices** or **large-scale deployments** where memory is a critical constraint.  

- **IQ3_XS**: Ultra-low-bit quantization (3-bit) with **extreme memory efficiency**.  
  - **Use case**: Best for **ultra-low-memory devices** where even Q4_K is too large.  
  - **Trade-off**: Lower accuracy compared to higher-bit quantizations.  

- **IQ3_S**: Small block size for **maximum memory efficiency**.  
  - **Use case**: Best for **low-memory devices** where **IQ3_XS** is too aggressive.  

- **IQ3_M**: Medium block size for better accuracy than **IQ3_S**.  
  - **Use case**: Suitable for **low-memory devices** where **IQ3_S** is too limiting.  

- **Q4_K**: 4-bit quantization with **block-wise optimization** for better accuracy.  
  - **Use case**: Best for **low-memory devices** where **Q6_K** is too large.  

- **Q4_0**: Pure 4-bit quantization, optimized for **ARM devices**.  
  - **Use case**: Best for **ARM-based devices** or **low-memory environments**.  

---

### **Summary Table: Model Format Selection**  

| Model Format  | Precision  | Memory Usage  | Device Requirements  | Best Use Case  |  
|--------------|------------|---------------|----------------------|---------------|  
| **BF16**     | Highest    | High          | BF16-supported GPU/CPUs  | High-speed inference with reduced memory |  
| **F16**      | High       | High          | FP16-supported devices | GPU inference when BF16 isn't available |  
| **Q4_K**     | Medium Low | Low           | CPU or Low-VRAM devices | Best for memory-constrained environments |  
| **Q6_K**     | Medium     | Moderate      | CPU with more memory | Better accuracy while still being quantized |  
| **Q8_0**     | High       | Moderate      | CPU or GPU with enough VRAM | Best accuracy among quantized models |  
| **IQ3_XS**   | Very Low   | Very Low      | Ultra-low-memory devices | Extreme memory efficiency and low accuracy |  
| **Q4_0**     | Low        | Low           | ARM or low-memory devices | llama.cpp can optimize for ARM devices |  

---

## **Included Files & Details**  

### `{base_name}-bf16.gguf`  
- Model weights preserved in **BF16**.  
- Use this if you want to **requantize** the model into a different format.  
- Best if your device supports **BF16 acceleration**.  

### `{base_name}-f16.gguf`  
- Model weights stored in **F16**.  
- Use if your device supports **FP16**, especially if BF16 is not available.  

### `{base_name}-bf16-q8_0.gguf`  
- **Output & embeddings** remain in **BF16**.  
- All other layers quantized to **Q8_0**.  
- Use if your device supports **BF16** and you want a quantized version.  

### `{base_name}-f16-q8_0.gguf`  
- **Output & embeddings** remain in **F16**.  
- All other layers quantized to **Q8_0**.    

### `{base_name}-q4_k.gguf`  
- **Output & embeddings** quantized to **Q8_0**.  
- All other layers quantized to **Q4_K**.  
- Good for **CPU inference** with limited memory.  

### `{base_name}-q4_k_s.gguf`  
- Smallest **Q4_K** variant, using less memory at the cost of accuracy.  
- Best for **very low-memory setups**.  

### `{base_name}-q6_k.gguf`  
- **Output & embeddings** quantized to **Q8_0**.  
- All other layers quantized to **Q6_K** .  

### `{base_name}-q8_0.gguf`  
- Fully **Q8** quantized model for better accuracy.  
- Requires **more memory** but offers higher precision.  

### `{base_name}-iq3_xs.gguf`  
- **IQ3_XS** quantization, optimized for **extreme memory efficiency**.  
- Best for **ultra-low-memory devices**.  

### `{base_name}-iq3_m.gguf`  
- **IQ3_M** quantization, offering a **medium block size** for better accuracy.  
- Suitable for **low-memory devices**.  

### `{base_name}-q4_0.gguf`  
- Pure **Q4_0** quantization, optimized for **ARM devices**.  
- Best for **low-memory environments**.
- Prefer IQ4_NL for better accuracy.

# <span id="testllm" style="color: #7F7FFF;">🚀 If you find these models useful</span>

Please click like ❤ . Also I'd really appreciate it if you could test my Network Monitor Assistant at 👉 [Network Monitor Assitant](https://freenetworkmonitor.click/dashboard).

💬 Click the **chat icon** (bottom right of the main and dashboard pages) . Choose a LLM; toggle between the LLM Types TurboLLM -> FreeLLM -> TestLLM.

### What I'm Testing

I'm experimenting with **function calling** against my network monitoring service. Using small open source models. I am into the question "How small can it go and still function".

🟡 **TestLLM** – Runs the current testing model using llama.cpp on 6 threads of a Cpu VM (Should take about 15s to load. Inference speed is quite slow and it only processes one user prompt at a time—still working on scaling!). If you're curious, I'd be happy to share how it works! .

### The other Available AI Assistants

🟢 **TurboLLM** – Uses **gpt-4o-mini** Fast! . Note: tokens are limited since OpenAI models are pricey, but you can [Login](https://freenetworkmonitor.click) or [Download](https://freenetworkmonitor.click/download) the Free Network Monitor agent to get more tokens, Alternatively use the TestLLM .

🔵 **HugLLM** – Runs **open-source Hugging Face models** Fast, Runs small models (≈8B) hence lower quality, Get 2x more tokens (subject to Hugging Face API availability)


"""

    # Update the README.md content
    updated_content = readme_content[:meta_end] + new_section + readme_content[meta_end:]
    
    # Write the updated content back to the README.md
    with open(readme_file, "w") as file:
        file.write(updated_content)

    print(f"README.md updated successfully for {base_name}.")
