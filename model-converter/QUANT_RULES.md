# Tensor precision rules

`quant_rules.json` matches the cleaned GGUF tensor names (without `.weight`),
not the original Hugging Face module names. Rules select precision; llama.cpp
still decides whether a tensor is eligible and whether its shape supports it.
Generated tensor expressions are escaped and anchored to avoid prefix matches.

## Native precision floor

For mixed presets, the converter first runs the selected llama-quantize binary
with `--dry-run`, using the same preset, importance matrix, and embedding/output
settings. Protective ladder bumps are emitted only when their storage precision
exceeds the native choice. For example, an edge-layer Q5_K suggestion no longer
replaces a native Q6_K FFN down projection. Equal-width and unknown native formats
retain the native choice; bit width is a conservative ordering, not an accuracy
measurement. Explicit `force_type` and F16/BF16/F32 overrides remain authoritative.

Pure presets have no native mixing to preserve and skip this step. NVFP4 and
MXFP4_MOE retain their existing paths. A failed or unreadable native dry run stops
the mixed conversion rather than silently applying potentially lower precision.
This requires a llama-quantize build with `--dry-run` support. The values below
describe rule suggestions; final mixed-preset choices can be higher.

## NVFP4 selection

NVFP4 selects standard attention `attn_q`, `attn_k`, `attn_v`, `attn_qkv`,
and `attn_output`, together with dense FFN, routed/shared/chunked experts, and
fused expert gate/up weights. This applies to dense and MoE models.

Other eligible weights default to Q8_0, including embeddings, the LM head,
low-rank attention variants, fused `attn_qkv_gate`, and recurrent projections.
Existing explicit precision overrides still apply. Selecting NVFP4 weights
does not change the runtime KV-cache format or enable an FP4 attention kernel.
Tensor names alone cannot distinguish every hybrid architecture that reuses
standard attention names; model-level accuracy remains to be evaluated.

## Added coverage

| New tensor names | Policy |
| --- | --- |
| `ffn_gate_up_exps` | Inherit gate/up expert bumps once per matching rule, including layer-order adjustments and opt-in full-precision overrides. |
| `ffn_gate_chexps`, `ffn_up_chexps`, `ffn_down_chexps` | Inherit the corresponding routed expert policy, not the shared expert policy. |
| `attn_qkv_gate` | Q8_0 for NVFP4; otherwise inherit fused QKV policy; a fused tensor cannot use separate precision for its QKV and gate slices. |
| `shortconv.in_proj`, `shortconv.out_proj` | Inherit existing SSM input/output projection policy. |
| `time_mix_key`, `time_mix_value`, `time_mix_output` | Q8_0 for NVFP4; otherwise use attention key/value/output rules as a role-based starting policy. |
| `channel_mix_key`, `channel_mix_value` | Use FFN up/down rules for non-NVFP4 presets. Keep the existing Q8_0 default for NVFP4 until evaluated. |
| `ssm_x`, `ssm_dt`, `ssm_f_a`, `ssm_f_b`, `ssm_g_a`, `ssm_g_b` | Q8_0 for quantized presets; existing opt-in F16/BF16 mode may override this. |
| `attn_gate` | Q8_0 for NVFP4; otherwise inherit attention value/QKV bumps based on the main quant and layer order, subject to the native precision floor. |
| `time_mix_receptance`, `time_mix_gate` | Inherit `time_mix_value` bumps; retain Q8_0 for NVFP4 and existing full-precision overrides. |
| `channel_mix_receptance` | Inherit `channel_mix_value` bumps; retain Q8_0 for NVFP4 and existing full-precision overrides. |
| `ffn_gate_inp_shexp` | Same Q8_0 control/gate policy. |
| `ssm_beta_alpha` | Extend the existing `ssm_alpha` / `ssm_beta` F32 exception to the fused control projection. |

This transfers the current bump values to equivalent roles, rather than adding
an independently tuned bit width for every architecture. In particular, no
extra expert bump is accumulated twice just because a tensor fuses gate and up.

For example, at an edge layer (normalized order 0), with `is_moe=True`:

| Base preset | Fused gate/up experts | Chunked down experts | SSM dt control |
| --- | --- | --- | --- |
| Q1_0 | IQ1_M | IQ2_XS | Q8_0 |
| IQ2_XS | IQ3_XXS | IQ3_XXS | Q8_0 |
| IQ3_S | IQ4_NL | IQ4_XS | Q8_0 |
| Q2_K | Q3_K | Q3_K | Q8_0 |
| Q3_K | Q4_K | Q4_K | Q8_0 |
| Q4_K | Q5_K | Q5_K | Q8_0 |
| Q5_K | Q6_K | Q6_K | Q8_0 |
| Q6_K | Native base handling | Native base handling | Q8_0 |
| Q8_0 | Native base handling | Native base handling | Q8_0 |
| NVFP4 | NVFP4 | NVFP4 | Q8_0 |

Middle-layer results differ according to the existing layer-order rules.
Legacy Q4_0/Q4_1/Q5_0/Q5_1 presets retain native treatment of large projections,
with the new Q8_0 control/gate exceptions. No ladder bumps are invented for
those families. Full-precision F16/BF16 presets are not in the Q8_0 rule.
`MXFP4_MOE` continues to delegate mixing to llama.cpp and bypasses these rules.

## Evidence and limits

The tensor roles and exclusions were checked against the installed llama.cpp
source and upstream:

- [GGUF tensor definitions](https://github.com/ggml-org/llama.cpp/blob/master/gguf-py/gguf/constants.py)
- [Gate/up fusion during conversion](https://github.com/ggml-org/llama.cpp/blob/master/conversion/base.py)
- [Chunked expert graph](https://github.com/ggml-org/llama.cpp/blob/master/src/models/grovemoe.cpp)
- [Quantizer eligibility and precision selection](https://github.com/ggml-org/llama.cpp/blob/master/src/llama-quant.cpp)

Llama.cpp already excludes norms, small SSM/short-convolution kernels, routing
tables, and several RWKV control tensors. Those exclusions remain authoritative;
a rule does not force an otherwise ineligible tensor to become quantized.

The Q8_0 control rule and projection analogies are conservative engineering
choices, not measured per-model optima. The tests verify rule selection,
boundaries, expert flags, exact tensor matching, and override precedence.
Perplexity/task evaluations on actual model families are still needed before
calling these settings quality-validated. Unknown architectures are not covered
merely because their names match a familiar suffix.
