---
license: gemma
library_name: transformers
pipeline_tag: image-text-to-text
extra_gated_heading: Access Gemma on Hugging Face
extra_gated_prompt: >-
  To access Gemma on Hugging Face, you’re required to review and agree to
  Google’s usage license. To do this, please ensure you’re logged in to Hugging
  Face and click below. Requests are processed immediately.
extra_gated_button_content: Acknowledge license
base_model: google/gemma-3-4b-pt
---

# ShieldGemma 2 model card

**Model Page**: [ShieldGemma](https://ai.google.dev/gemma/docs/shieldgemma)

**Resources and Technical Documentation**:

- [Responsible Generative AI Toolkit](https://ai.google.dev/responsible)
- [ShieldGemma on Hugging Face Hub](https://huggingface.co/models?search=shieldgemma)

**Terms of Use**: [Terms](https://ai.google.dev/gemma/terms)

**Authors**: Google

## Model Information

ShieldGemma 2 is a model trained on Gemma 3's 4B IT checkpoint for image safety classification across key categories that takes in images and outputs safety labels per policy.

### Description

ShieldGemma 2, built on [Gemma 3](https://ai.google.dev/gemma/docs/core/model_card_3), is a 4 billion (4B) parameter
model that checks the safety of both synthetic and natural images against key categories to help you build robust
datasets and models. With this addition to the Gemma family of models, researchers and developers can now easily
minimize the risk of harmful content in their models across key areas of harm as defined below:

-   No Sexually Explicit content: The image shall not contain content that depicts explicit or graphic sexual acts
    (e.g., pornography, erotic nudity, depictions of rape or sexual assault).
-   No Dangerous Content: The image shall not contain content that facilitates or encourages activities that could
    cause real-world harm (e.g., building firearms and explosive devices, promotion of terrorism, instructions for
    suicide).
-   No Violence/Gore content: The image shall not contain content that depicts shocking, sensational, or gratuitous
    violence (e.g., excessive blood and gore, gratuitous violence against animals, extreme injury or moment of death).

We recommend using ShieldGemma 2 as an input filter to vision language models, or as an output filter of image
generation systems. To train a robust image safety model, we curated training datasets of natural and synthetic images
and instruction-tuned Gemma 3 to demonstrate strong performance. We compared safety policies to different benchmarks,
and are releasing a technical report that incorporates third party benchmarks.

### Inputs and outputs

Here is our prompt instruction:

```
You are a policy expert trying to help determine whether a generated or real image is in violation of the safety policy
below. Your decision must very clearly follow the specific language used in the safety policy and should not include
any interpretation outside of the safety policy.

<BEGIN_SAFETY_POLICY>
{policy}
</END_SAFETY_POLICY>

Does the image violate the above policy? Your Answer must start with with 'Yes' or 'No'.
```

- **Input:** Image \+ Prompt Instruction with policy definition above
- **Output:** Probability of 'Yes'/'No' tokens, with a higher score indicating the model's higher confidence that the
image violates the specified policy. 'Yes' means that the image violated the policy, 'No' means that the model did not
violate the policy.

### Usage

Below there are some code snippets on how to get quickly started with running the model. First, install the
Transformers library with the version made for Gemma 3:

```sh

$ pip install -U transformers

```

Then, copy the snippet from the section that is relevant for your use case.

#### Running the model on a single/multi GPU

```python
# pip install accelerate

from transformers import AutoProcessor, ShieldGemma2ForImageClassification
from PIL import Image
import requests
import torch

model_id = "google/shieldgemma-2-4b-it"

url = "https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/bee.jpg"
image = Image.open(requests.get(url, stream=True).raw)

model = ShieldGemma2ForImageClassification.from_pretrained(model_id).eval()
processor = AutoProcessor.from_pretrained(model_id)

model_inputs = processor(images=[image], return_tensors="pt")

with torch.inference_mode():
    scores = model(**model_inputs)

print(scores.probabilities)
```

### Citation

```
@article{shieldgemma2,
    title={ShieldGemma 2},
    url={https://ai.google.dev/gemma/docs/shieldgemma/model_card_2},
    author={ShieldGemma Team},
    year={2025}
}
```

## Model Data

### Training Dataset

Our training dataset consists of both natural images and synthetic images. For natural images, we sample a subset of
images from the [WebLI](https://arxiv.org/abs/2209.06794) (Web Language and Image) dataset that are relevant to the
safety tasks. For synthetic images, we leverage an internal data generation pipeline to enable controlled generation of
prompts and corresponding images that balance the diversity and severity of images that target dangerous content,
sexually explicit, and violent content in English only. Our data generation taxonomy diversely ranges over a number of
dimensions including demographics, context, regional aspects, and more.

### **Data Preprocessing**

Here are the key data cleaning and filtering methods applied to the training data:

-   CSAM Filtering: CSAM (Child Sexual Abuse Material) filtering was applied in the data preparation process to ensure
    the exclusion of illegal content.

## **Implementation Information**

### **Hardware**

ShieldGemma 2 was trained using the latest generation of
[Tensor Processing Unit (TPU)](https://cloud.google.com/tpu/docs/intro-to-tpu) hardware (TPUv5e), for more details
refer to the [Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3).

### **Software**

Training was done using [JAX](https://github.com/jax-ml/jax) and
[ML Pathways](https://blog.google/technology/ai/introducing-pathways-next-generation-ai-architecture/). For more
details refer to the [Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3).

## **Evaluation**

## Model evaluation metrics and results.

ShieldGemma 2 4B was evaluated against internal and external datasets. Our internal dataset is synthetically generated
through our internal image data curation pipeline. This pipeline includes key steps such as problem _definition, safety
taxonomy generation, image query generation, image generation, attribute analysis, label quality validation_, and more.
We have approximately 500 examples for each harm policy. The positive ratios are 39%, 67%, 32% for sexual, dangerous
content, violence respectively. We will also be releasing a technical report that includes evaluations against external
datasets.

**Internal Benchmark Evaluation Results**

|                         | Sexually Explicit  | Dangerous Content  | Violence & Gore    |
| :---------------------- | :----------------- | :----------------- | :----------------- |
| LlavaGuard 7B           | 47.6/93.1/63.0     | 67.8/47.2/55.7     | 36.8/100.0/53.8    |
| GPT-4o mini             | 68.3/97.7/80.3     | 84.4/99.0/91.0     | 40.2/100.0/57.3    |
| Gemma-3-4B-IT           | 77.7/87.9/82.5     | 75.9/94.5/84.2     | 78.2/82.2/80.1     |
| **shieldgemma-2-4b-it** | 87.6/89.7/**88.6** | 95.6/91.9/**93.7** | 80.3/90.4/**85.0** |

Table 1: Result format–precision/recall/optimal F1 (%, higher is better). Evaluation results on our internal benchmarks
shows ShieldGemma 2 outperforming external baseline models.

**Ethics and Safety**

Ethics and safety evaluation approach and results.

### **Evaluation Approach**

Although the ShieldGemma 2 models are nominally generative models, they are designed to run in _scoring mode_ to
predict the probability that the next token would be `Yes` or `No`. Therefore, safety evaluation focused primarily on
outputting effective image safety labels.

### **Evaluation Results**

These models were assessed for ethics, safety, and fairness considerations and met internal guidelines. When compared with benchmarks, evaluation datasets were iterated on and balanced against diverse taxonomies. Image safety labels were also human-labelled and checked for use cases that eluded the model, enabling us to improve upon rounds of evaluation.

**Usage and Limitations**

These models have certain limitations that users should be aware of.

### **Intended Usage**

ShieldGemma 2 is intended to be used as a safety content moderator, either for human user inputs, model outputs, or both. These models are part of the [Responsible Generative AI Toolkit](https://ai.google.dev/responsible), which is a set of recommendations, tools, datasets and models aimed to improve the safety of AI applications as part of the Gemma ecosystem.

### **Limitations**

All the usual limitations for large language models apply, see the [Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3) for more details. Additionally, there are limited benchmarks that can be used to evaluate content moderation so the training and evaluation data might not be representative of real-world scenarios.

ShieldGemma 2 is also highly sensitive to the specific user-provided description of safety principles, and might perform unpredictably under conditions that require a good understanding of language ambiguity and nuance.

As with other models that are part of the Gemma ecosystem, ShieldGemma 2 is subject to Google's [prohibited use policies](https://ai.google.dev/gemma/prohibited_use_policy).

### **Ethical Considerations and Risks**

The development of large language models (LLMs) raises several ethical concerns. We have carefully considered multiple aspects in the development of these models.

Refer to the [Gemma 3 model card](https://ai.google.dev/gemma/docs/core/model_card_3) for more details.

### **Benefits**

At the time of release, this family of models provides high-performance open large language model implementations designed from the ground up for Responsible AI development compared to similarly sized models.

Using the benchmark evaluation metrics described in this document, these models have been shown to provide superior performance to other, comparably-sized open model alternatives.
