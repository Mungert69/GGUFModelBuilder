---
license: apache-2.0
license_link: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/main/LICENSE
language:
- en
pipeline_tag: text-generation
base_model: Qwen/Qwen2.5-0.5B
tags:
- chat
library_name: transformers
---

# <span style="color: #7FFF7F;">Qwen2.5-0.5B-Instruct GGUF Models</span>

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

### `Qwen2.5-0.5B-Instruct-bf16.gguf`  
- Model weights preserved in **BF16**.  
- Use this if you want to **requantize** the model into a different format.  
- Best if your device supports **BF16 acceleration**.  

### `Qwen2.5-0.5B-Instruct-f16.gguf`  
- Model weights stored in **F16**.  
- Use if your device supports **FP16**, especially if BF16 is not available.  

### `Qwen2.5-0.5B-Instruct-bf16-q8_0.gguf`  
- **Output & embeddings** remain in **BF16**.  
- All other layers quantized to **Q8_0**.  
- Use if your device supports **BF16** and you want a quantized version.  

### `Qwen2.5-0.5B-Instruct-f16-q8_0.gguf`  
- **Output & embeddings** remain in **F16**.  
- All other layers quantized to **Q8_0**.    

### `Qwen2.5-0.5B-Instruct-q4_k.gguf`  
- **Output & embeddings** quantized to **Q8_0**.  
- All other layers quantized to **Q4_K**.  
- Good for **CPU inference** with limited memory.  

### `Qwen2.5-0.5B-Instruct-q4_k_s.gguf`  
- Smallest **Q4_K** variant, using less memory at the cost of accuracy.  
- Best for **very low-memory setups**.  

### `Qwen2.5-0.5B-Instruct-q6_k.gguf`  
- **Output & embeddings** quantized to **Q8_0**.  
- All other layers quantized to **Q6_K** .  

### `Qwen2.5-0.5B-Instruct-q8_0.gguf`  
- Fully **Q8** quantized model for better accuracy.  
- Requires **more memory** but offers higher precision.  

### `Qwen2.5-0.5B-Instruct-iq3_xs.gguf`  
- **IQ3_XS** quantization, optimized for **extreme memory efficiency**.  
- Best for **ultra-low-memory devices**.  

### `Qwen2.5-0.5B-Instruct-iq3_m.gguf`  
- **IQ3_M** quantization, offering a **medium block size** for better accuracy.  
- Suitable for **low-memory devices**.  

### `Qwen2.5-0.5B-Instruct-q4_0.gguf`  
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




# Qwen2.5-0.5B-Instruct

## Introduction

Qwen2.5 is the latest series of Qwen large language models. For Qwen2.5, we release a number of base language models and instruction-tuned language models ranging from 0.5 to 72 billion parameters. Qwen2.5 brings the following improvements upon Qwen2:

- Significantly **more knowledge** and has greatly improved capabilities in **coding** and **mathematics**, thanks to our specialized expert models in these domains.
- Significant improvements in **instruction following**, **generating long texts** (over 8K tokens), **understanding structured data** (e.g, tables), and **generating structured outputs** especially JSON. **More resilient to the diversity of system prompts**, enhancing role-play implementation and condition-setting for chatbots.
- **Long-context Support** up to 128K tokens and can generate up to 8K tokens.
- **Multilingual support** for over 29 languages, including Chinese, English, French, Spanish, Portuguese, German, Italian, Russian, Japanese, Korean, Vietnamese, Thai, Arabic, and more. 

**This repo contains the instruction-tuned 0.5B Qwen2.5 model**, which has the following features:
- Type: Causal Language Models
- Training Stage: Pretraining & Post-training
- Architecture: transformers with RoPE, SwiGLU, RMSNorm, Attention QKV bias and tied word embeddings
- Number of Parameters: 0.49B
- Number of Paramaters (Non-Embedding): 0.36B
- Number of Layers: 24
- Number of Attention Heads (GQA): 14 for Q and 2 for KV
- Context Length: Full 32,768 tokens and generation 8192 tokens

For more details, please refer to our [blog](https://qwenlm.github.io/blog/qwen2.5/), [GitHub](https://github.com/QwenLM/Qwen2.5), and [Documentation](https://qwen.readthedocs.io/en/latest/).

## Requirements

The code of Qwen2.5 has been in the latest Hugging face `transformers` and we advise you to use the latest version of `transformers`.

With `transformers<4.37.0`, you will encounter the following error:
```
KeyError: 'qwen2'
```

## Quickstart

Here provides a code snippet with `apply_chat_template` to show you how to load the tokenizer and model and how to generate contents.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "Qwen/Qwen2.5-0.5B-Instruct"

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(model_name)

prompt = "Give me a short introduction to large language model."
messages = [
    {"role": "system", "content": "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."},
    {"role": "user", "content": prompt}
]
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)
model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

generated_ids = model.generate(
    **model_inputs,
    max_new_tokens=512
)
generated_ids = [
    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
]

response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
```


## Evaluation & Performance

Detailed evaluation results are reported in this [📑 blog](https://qwenlm.github.io/blog/qwen2.5/).

For requirements on GPU memory and the respective throughput, see results [here](https://qwen.readthedocs.io/en/latest/benchmark/speed_benchmark.html).

## Citation

If you find our work helpful, feel free to give us a cite.

```
@misc{qwen2.5,
    title = {Qwen2.5: A Party of Foundation Models},
    url = {https://qwenlm.github.io/blog/qwen2.5/},
    author = {Qwen Team},
    month = {September},
    year = {2024}
}

@article{qwen2,
      title={Qwen2 Technical Report}, 
      author={An Yang and Baosong Yang and Binyuan Hui and Bo Zheng and Bowen Yu and Chang Zhou and Chengpeng Li and Chengyuan Li and Dayiheng Liu and Fei Huang and Guanting Dong and Haoran Wei and Huan Lin and Jialong Tang and Jialin Wang and Jian Yang and Jianhong Tu and Jianwei Zhang and Jianxin Ma and Jin Xu and Jingren Zhou and Jinze Bai and Jinzheng He and Junyang Lin and Kai Dang and Keming Lu and Keqin Chen and Kexin Yang and Mei Li and Mingfeng Xue and Na Ni and Pei Zhang and Peng Wang and Ru Peng and Rui Men and Ruize Gao and Runji Lin and Shijie Wang and Shuai Bai and Sinan Tan and Tianhang Zhu and Tianhao Li and Tianyu Liu and Wenbin Ge and Xiaodong Deng and Xiaohuan Zhou and Xingzhang Ren and Xinyu Zhang and Xipin Wei and Xuancheng Ren and Yang Fan and Yang Yao and Yichang Zhang and Yu Wan and Yunfei Chu and Yuqiong Liu and Zeyu Cui and Zhenru Zhang and Zhihao Fan},
      journal={arXiv preprint arXiv:2407.10671},
      year={2024}
}
```