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

---

## <span style="color: #7FFF7F;">Quantization Beyond the IMatrix</span>

I've been experimenting with a new quantization approach that selectively elevates the precision of key layers beyond what the default IMatrix configuration provides.

In my testing, standard IMatrix quantization underperforms at lower bit depths, especially with Mixture of Experts (MoE) models. To address this, I'm using the `--tensor-type` option in `llama.cpp` to manually "bump" important layers to higher precision. You can see the implementation here:  
👉 [Layer bumping with llama.cpp](https://github.com/Mungert69/GGUFModelBuilder/blob/main/model-converter/tensor_list_builder.py)

While this does increase model file size, it significantly improves precision for a given quantization level.

### **I'd love your feedback—have you tried this? How does it perform for you?**

"""

explain_section = """
---

<a href="https://readyforquantum.com/huggingface_gguf_selection_guide.html" style="color: #7FFF7F;">
  Click here to get info on choosing the right GGUF model format
</a>

---

"""
like_section = """

<!--End Original Model Card-->

---

# <span id="testllm" style="color: #7F7FFF;">🚀 If you find these models useful</span>

Help me test my **AI-Powered Quantum Network Monitor Assistant** with **quantum-ready security checks**:  

👉 [Quantum Network Monitor](https://readyforquantum.com/?assistant=open&utm_source=huggingface&utm_medium=referral&utm_campaign=huggingface_repo_readme)  


The full Open Source Code for the Quantum Network Monitor Service available at my github repos ( repos with NetworkMonitor in the name) : [Source Code Quantum Network Monitor](https://github.com/Mungert69). You will also find the code I use to quantize the models if you want to do it yourself [GGUFModelBuilder](https://github.com/Mungert69/GGUFModelBuilder)

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
- **Create custom cmd processors to run .net code on Quantum Network Monitor Agents**
- **Real-time network diagnostics and monitoring**
- **Security Audits**
- **Penetration testing** (Nmap/Metasploit)  

🔵 **HugLLM** – Latest Open-source models:  
- 🌐 Runs on Hugging Face Inference API. Performs pretty well using the lastest models hosted on Novita.

### 💡 **Example commands you could test**:  
1. `"Give me info on my websites SSL certificate"`  
2. `"Check if my server is using quantum safe encyption for communication"`  
3. `"Run a comprehensive security audit on my server"`
4. '"Create a cmd processor to .. (what ever you want)" Note you need to install a [Quantum Network Monitor Agent](https://readyforquantum.com/Download/?utm_source=huggingface&utm_medium=referral&utm_campaign=huggingface_repo_readme) to run the .net code from. This is a very flexible and powerful feature. Use with caution!

### Final Word

I fund the servers used to create these model files, run the Quantum Network Monitor service, and pay for inference from Novita and OpenAI—all out of my own pocket. All the code behind the model creation and the Quantum Network Monitor project is [open source](https://github.com/Mungert69). Feel free to use whatever you find helpful.

If you appreciate the work, please consider [buying me a coffee](https://www.buymeacoffee.com/mahadeva) ☕. Your support helps cover service costs and allows me to raise token limits for everyone.

I'm also open to job opportunities or sponsorship.

Thank you! 😊
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

<!--Begin Original Model Card-->
"""


    # Update the README.md content
    updated_content = readme_content[:meta_end] + new_section + readme_content[meta_end:] + like_section
    
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
