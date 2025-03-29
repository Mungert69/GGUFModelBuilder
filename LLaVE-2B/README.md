---
pipeline_tag: image-text-to-text
library_name: transformers
license: apache-2.0
language:
- en
tags:
- Sentence Similarity
- Embedding
- zero-shot-image-classification
- video-text-to-text
base_model: BAAI/Aquila-VL-2B-llava-qwen
---

# LLaVE-2B

## Model Summary

The LLaVE models are 2B parameter multimodal embedding models based on the Aquila-VL-2B model with a context window of 4K tokens.

- **Repository:** [LLaVE](https://github.com/DeepLearnXMU/LLaVE)
- **Paper:** [LLaVE](https://huggingface.co/papers/2503.04812)

## Train/Eval Data
 - Train data: https://huggingface.co/datasets/TIGER-Lab/MMEB-train
 - Eval data: https://huggingface.co/datasets/TIGER-Lab/MMEB-eval

## Use

### Intended use

The model have the ability to embed with texts, images, multi-image and videos. 

## MMEB Leaderboard
We achieved the top ranking on the MMEB leaderboard using only a small amount of data.

![MMEB Leaderboard](./figures/leaderboard.png)


## Model Performance
LLaVE-2B achieved excellent performance on MMEB using fewer parameters and 662K training pairs.
![MMEB](./figures/results.png)

Although LLaVE is trained on image-text data, it can generalize to text-video retrieval tasks in a zero-shot manner and achieve strong performance, demonstrating its remarkable potential for transfer to other embedding tasks.
<img src="./figures/zero-shot-vr.png" alt="video-retrieve" width="400" height="auto">

### Quick Start

First clone our github
```bash
git clone https://github.com/DeepLearnXMU/LLaVE
cd LLaVE
pip install -e ".[train]"
```

We provide the simple embedding process for using our model. For more details, you could refer to [Github](https://github.com/DeepLearnXMU/LLaVE).

```python
# pip install git+https://github.com/DeepLearnXMU/LLaVE


import torch
import copy
from PIL import Image
from llava.constants import IMAGE_TOKEN_INDEX, DEFAULT_IMAGE_TOKEN
from llava.conversation import conv_templates
from llava.model.builder import load_pretrained_model
from llava.mm_utils import tokenizer_image_token, process_images

pretrained = "zhibinlan/LLaVE-2B"
model_name = "llava_qwen"
device = "cuda"
device_map = "auto"
tokenizer, model, image_processor, max_length = load_pretrained_model(pretrained, None, model_name, device_map=device_map)  # Add any other thing you want to pass in llava_model_args
model.eval()

# Image + Text -> Text
image = Image.open("figures/example.jpg")
image_tensor = process_images([image], image_processor, model.config)
image_tensor = [_image.to(dtype=torch.float16, device=device) for _image in image_tensor]
conv_template = "qwen_1_5"  # Make sure you use correct chat template for different models

question = DEFAULT_IMAGE_TOKEN + " Represent the given image with the following question: What is in the image"
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], question)
conv.append_message(conv.roles[1], "\n")
prompt_question = conv.get_prompt()
input_ids = tokenizer_image_token(prompt_question, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt").unsqueeze(0).to(device)
attention_mask=input_ids.ne(tokenizer.pad_token_id)
image_sizes = [image.size]
query_embed = model.encode_multimodal_embeddings(input_ids, attention_mask=attention_mask,images=image_tensor, image_sizes=image_sizes)

target_string = "A cat and a dog"
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], target_string)
conv.append_message(conv.roles[1], "\n")
target_string = conv.get_prompt()
target_input_ids = tokenizer(target_string, return_tensors="pt").input_ids.to(device)
attention_mask=target_input_ids.ne(tokenizer.pad_token_id)
target_embed = model.encode_multimodal_embeddings(target_input_ids, attention_mask=attention_mask)

print("A cat and a dog similarity score: ", query_embed @ target_embed.T)
# 2B: A cat and a dog similarity score: tensor([[0.5132]]

neg_string = "A cat and a tiger"
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], neg_string)
conv.append_message(conv.roles[1], "\n")
neg_string = conv.get_prompt()
neg_input_ids = tokenizer(neg_string, return_tensors="pt").input_ids.to(device)
attention_mask=neg_input_ids.ne(tokenizer.pad_token_id)
neg_embed = model.encode_multimodal_embeddings(neg_input_ids, attention_mask=attention_mask)
print("A cat and a tiger similarity score: ", query_embed @ neg_embed.T)
# 2B: A cat and a tiger similarity score: tensor([[0.3809]]


# Text -> Image
pos_string = "Find me an everyday image that matches the given caption: A cat and a dog."
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], pos_string)
conv.append_message(conv.roles[1], "\n")
pos_string = conv.get_prompt()
pos_input_ids = tokenizer(pos_string, return_tensors="pt").input_ids.to(device)
attention_mask=pos_input_ids.ne(tokenizer.pad_token_id)
pos_query_embed = model.encode_multimodal_embeddings(pos_input_ids, attention_mask=attention_mask)

target = DEFAULT_IMAGE_TOKEN + " Represent the given image."
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], target)
conv.append_message(conv.roles[1], "\n")
prompt_target = conv.get_prompt()
target_input_ids = tokenizer_image_token(prompt_target, tokenizer, IMAGE_TOKEN_INDEX, return_tensors="pt").unsqueeze(0).to(device)
attention_mask=target_input_ids.ne(tokenizer.pad_token_id)
target_image_sizes = [image.size]
target_embed = model.encode_multimodal_embeddings(target_input_ids, attention_mask=attention_mask,images=image_tensor, image_sizes=target_image_sizes)

print("A cat and a dog image similarity score: ", pos_query_embed @ target_embed.T)
# 2B: A cat and a dog similarity score: tensor([[0.5225]]

neg_string = "Find me an everyday image that matches the given caption: A cat and a tiger."
conv = copy.deepcopy(conv_templates[conv_template])
conv.append_message(conv.roles[0], neg_string)
conv.append_message(conv.roles[1], "\n")
neg_string = conv.get_prompt()
neg_input_ids = tokenizer(neg_string, return_tensors="pt").input_ids.to(device)
attention_mask=neg_input_ids.ne(tokenizer.pad_token_id)
neg_query_embed = model.encode_multimodal_embeddings(neg_input_ids, attention_mask=attention_mask)

print("A cat and a tiger image similarity score: ", neg_query_embed @ target_embed.T)
# 2B: A cat and a dog similarity score: tensor([[0.4141]]
```

## Hardware & Software
- **GPUs:** 8 * Nvidia A100 (40G) (for whole model training)
- **Orchestration:** [Huggingface Trainer](https://huggingface.co/docs/transformers/main_classes/trainer)
- **Neural networks:** [PyTorch](https://github.com/pytorch/pytorch)

## Citation
```
@article{lan2025llave,
  title={LLaVE: Large Language and Vision Embedding Models with Hardness-Weighted Contrastive Learning},
  author={Lan, Zhibin and Niu, Liqiang and Meng, Fandong and Zhou, Jie and Su, Jinsong},
  journal={arXiv preprint arXiv:2503.04812},
  year={2025}
}
```