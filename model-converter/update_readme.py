"""
update_readme.py

This script provides a function to update the README.md file in a model directory with
detailed information about the model, quantization methods, and hardware recommendations.
It can also add a section about ultra-low-bit quantization (IQ-DynamicGate) if requested.

Main Features:
- Inserts model generation details, including the llama.cpp commit hash.
- Adds a section on ultra-low-bit quantization if specified.
- Provides guidance on choosing the right model format for different hardware.
- Summarizes included files and their quantization types.
- Appends a call-to-action for users to test and provide feedback.

Functions:
    - update_readme(model_dir, base_name, add_iquant_txt=False): Updates the README.md file.
    - get_git_commit_info(repo_path): Returns the full and short git commit hashes for a repo.

Usage:
    python update_readme.py <model_dir> <base_name> [--iquant]

Arguments:
    model_dir: Path to the model directory containing README.md.
    base_name: Base name of the model (used for file references).
    --iquant: Optional flag to add the IQ-DynamicGate quantization section.

Exits with code 0 on success, raises exceptions on failure.
"""

import os
import subprocess

iquant_section_content = """
## <span style="color: #7FFF7F;"> Quantization beyond the IMatrix</span>

Tesintg a new quantization method using rules to bump important layers above what the standard imatrix would use.

I have found that the standard IMatrix does not perform very well at low bit quantiztion and for MOE models. So I am using llama.cpp --tensor-type to bump up selected layers. See [Layer bumping with llama.cpp](https://github.com/Mungert69/GGUFModelBuilder/blob/main/model-converter/tensor_list_builder.py)

This does create larger model files but the increases precision for a given model size.

### **Please provide feedback on how you find this method compares performs**

"""

explain_section = """
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

### **Hybrid Precision Models (e.g., `bf16_q8_0`, `f16_q4_K`) – Best of Both Worlds**  
These formats selectively **quantize non-essential layers** while keeping **key layers in full precision** (e.g., attention and output layers).

- Named like `bf16_q8_0` (meaning **full-precision BF16 core layers + quantized Q8_0 other layers**).  
- Strike a **balance between memory efficiency and accuracy**, improving over fully quantized models without requiring the full memory of BF16/F16.  

📌 **Use Hybrid Models if:**  
✔ You need **better accuracy than quant-only models** but can’t afford full BF16/F16 everywhere.  
✔ Your device supports **mixed-precision inference**.  
✔ You want to **optimize trade-offs** for production-grade models on constrained hardware.  

📌 **Avoid Hybrid Models if:**  
❌ Your target device doesn’t support **mixed or full-precision acceleration**.  
❌ You are operating under **ultra-strict memory limits** (in which case use fully quantized formats).  

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
These models are optimized for **very high memory efficiency**, making them ideal for **low-power devices** or **large-scale deployments** where memory is a critical constraint.  

- **IQ3_XS**: Ultra-low-bit quantization (3-bit) with **very high memory efficiency**.  
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

### **Ultra Low-Bit Quantization (IQ1_S IQ1_M IQ2_S IQ2_M IQ2_XS IQ2_XSS)** 
- *Ultra-low-bit quantization (1 2-bit) with **extreme memory efficiency**.  
  - **Use case**: Best for  cases were you have to fit the model into very constrained memory
  - **Trade-off**: Very Low Accuracy. May not function as expected. Please test fully before using.

---

### **Summary Table: Model Format Selection**  


| Model Format             | Precision        | Memory Usage     | Device Requirements             | Best Use Case                                                |  
|--------------------------|------------------|------------------|----------------------------------|--------------------------------------------------------------|  
| **BF16**                 | Very High        | High             | BF16-supported GPU/CPU           | High-speed inference with reduced memory                    |  
| **F16**                  | High             | High             | FP16-supported GPU/CPU           | GPU inference when BF16 isn’t available                     |  
| **Q4_K**                 | Medium-Low       | Low              | CPU or Low-VRAM devices          | Memory-constrained inference                                |  
| **Q6_K**                 | Medium           | Moderate         | CPU with more memory             | Better accuracy with quantization                           |  
| **Q8_0**                 | High             | Moderate         | GPU/CPU with moderate VRAM       | Highest accuracy among quantized models                     |  
| **IQ3_XS**               | Low              | Very Low         | Ultra-low-memory devices         | Max memory efficiency, low accuracy                         |  
| **IQ3_S**                | Low              | Very Low         | Low-memory devices               | Slightly more usable than IQ3_XS                            |  
| **IQ3_M**                | Low-Medium       | Low              | Low-memory devices               | Better accuracy than IQ3_S                                  |  
| **Q4_0**                 | Low              | Low              | ARM-based/embedded devices       | Optimized for ARM inference                                 |  
| **Ultra Low-Bit (IQ1/2_*)** | Very Low      | Extremely Low     | Tiny edge/embedded devices        | Fit models in extremely tight memory; low accuracy           |  
| **Hybrid (e.g., `bf16_q8_0`)** | Medium–High | Medium           | Mixed-precision capable hardware | Balanced performance and memory, near-FP accuracy in critical layers |

---
"""
like_section = """
# <span id="testllm" style="color: #7F7FFF;">🚀 If you find these models useful</span>

Help me test my **AI-Powered Network Monitor Assistant** with **quantum-ready security checks**:  

👉 [Free Network Monitor](https://readyforquantum.com/dashboard/?assistant=open)  

The full Open Source Code for the Free Network Monitor Service available at my github repos ( repos with NetworkMonitor in the name) : [Source Code Free Network Monitor](https://github.com/Mungert69). You will also find the code I use to quantize the models if you want to do it yourself [GGUFModelBuilder](https://github.com/Mungert69/GGUFModelBuilder)

💬 **How to test**:  
 Choose an **AI assistant type**:  
   - `TurboLLM` (GPT-4.1-mini)  
   - `HugLLM` (Hugginface Open-source models)  
   - `TestLLM` (Experimental CPU-only)  

### **What I’m Testing**  
I’m pushing the limits of **small open-source models for AI network monitoring**, specifically:  
- **Function calling** against live network services  
- **How small can a model go** while still handling:  
  - Automated **Nmap security scans**  
  - **Quantum-readiness checks**  
  - **Network Monitoring tasks**  

🟡 **TestLLM** – Current experimental model (llama.cpp on 2 CPU threads on huggingface docker space):  
- ✅ **Zero-configuration setup**  
- ⏳ 30s load time (slow inference but **no API costs**) . No token limited as the cost is low.
- 🔧 **Help wanted!** If you’re into **edge-device AI**, let’s collaborate!  

### **Other Assistants**  
🟢 **TurboLLM** – Uses **gpt-4.1-mini** :
- **It performs very well but unfortunatly OpenAI charges per token. For this reason tokens usage is limited. 
- **Create custom cmd processors to run .net code on Free Network Monitor Agents**
- **Real-time network diagnostics and monitoring**
- **Security Audits**
- **Penetration testing** (Nmap/Metasploit)  

🔵 **HugLLM** – Latest Open-source models:  
- 🌐 Runs on Hugging Face Inference API. Performs pretty well using the lastest models hosted on Novita.

### 💡 **Example commands to you could test**:  
1. `"Give me info on my websites SSL certificate"`  
2. `"Check if my server is using quantum safe encyption for communication"`  
3. `"Run a comprehensive security audit on my server"`
4. '"Create a cmd processor to .. (what ever you want)" Note you need to install a Free Network Monitor Agent to run the .net code from. This is a very flexible and powerful feature. Use with caution!

"""
def update_readme(model_dir, base_name, add_iquant_txt=False):
    readme_file = os.path.join(model_dir, "README.md")
    
    # Check if README.md exists
    if not os.path.exists(readme_file):
        raise FileNotFoundError(f"README.md not found in {model_dir}")

    # Get Git commit info from llama.cpp repo
    llama_cpp_path = os.path.expanduser("~/code/models/llama.cpp")
    full_hash, short_hash = get_git_commit_info(llama_cpp_path)
    
    git_info = ""
    if short_hash:
        git_info = f"""
## <span style="color: #7F7FFF;">Model Generation Details</span>

This model was generated using [llama.cpp](https://github.com/ggerganov/llama.cpp) at commit [`{short_hash}`](https://github.com/ggerganov/llama.cpp/commit/{full_hash}).

"""
    # Read the existing content of the README.md
    with open(readme_file, "r") as file:
        readme_content = file.read()
    
    # Find where the metadata section ends (find the second occurrence of '---')
    meta_end = readme_content.find("---", readme_content.find("---") + 3) + 3  # Locate second '---'
    
    # The new content to be added after the metadata section
    iquant_section = ""
    if add_iquant_txt:
        iquant_section = iquant_section_content
 
    new_section = f"""

# <span style="color: #7FFF7F;">{base_name} GGUF Models</span>

{git_info}

{iquant_section}

{explain_section}

{like_section}

"""


    # Update the README.md content
    updated_content = readme_content[:meta_end] + new_section + readme_content[meta_end:]
    
    # Write the updated content back to the README.md
    with open(readme_file, "w") as file:
        file.write(updated_content)

    print(f"README.md updated successfully for {base_name}.")

def get_git_commit_info(repo_path):
    """Get short and full Git commit hash for a repository."""
    try:
        # Get full commit hash
        full_hash = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        
        # Get short commit hash (7 chars like GitHub)
        short_hash = subprocess.check_output(
            ["git", "-C", repo_path, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode("utf-8").strip()
        
        return full_hash, short_hash
    except subprocess.CalledProcessError:
        return None, None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("model_dir", help="Path to the model directory")
    parser.add_argument("base_name", help="Base name of the model")
    parser.add_argument("--iquant", action="store_true", help="Add iquant section")
    args = parser.parse_args()
    
    update_readme(args.model_dir, args.base_name, args.iquant)
