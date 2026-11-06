#!/usr/bin/env python3
"""
requant_tensors.py

Selectively requantize tensors in a GGUF file.

Tensors whose quantization type matches --match-quant are dequantized to f32
and then requantized to --target-quant. Every other tensor is copied verbatim
(raw bytes + metadata), so the rest of the model is untouched.

This follows the same read/modify/write pattern used by
gguf-py/gguf/scripts/update_gguf.py (wrapped by add_metadata_gguf.py): it reads
the source with GGUFReader (memory-mapped, so only one tensor is resident at a
time), copies all key/value metadata and the architecture, then writes a new
GGUF with GGUFWriter.

Usage:
    python requant_tensors.py <input.gguf> <output.gguf> \\
        --match-quant q8_0 --target-quant q4_0

Arguments:
    input:        Source GGUF file.
    output:       Destination GGUF file (will be created/overwritten).

Options:
    --match-quant: Quantization type of tensors to requantize (e.g. q8_0).
                   Required.
    --target-quant: Quantization type to convert matched tensors to
                    (e.g. q4_0, f16, bf16, q4_1, q5_0, q5_1). Required.
    --force:      Overwrite --output without prompting.
    --verbose:    Debug logging.

Notes:
    * Quantization targets that gguf-py can *encode* are: F32, F16, BF16,
      Q1_0, Q2_0, Q4_0, Q4_1, Q5_0, Q5_1, Q8_0, Q2_K, Q3_K, Q4_K, Q5_K,
      Q6_K, TQ1_0, TQ2_0 (and IQ/MXFP4/NVFP4 variants).
    * If --match-quant == --target-quant, matched tensors are copied verbatim
      (no generational loss).
    * Because the output is written to a separate file, you need roughly the
      size of the model in free disk space (input + output coexist briefly).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from tqdm import tqdm

# Prefer the local gguf-py (same convention as get_gguf_tensor_info.py and the
# gguf-py scripts).
local_gguf_path = Path.home() / "code" / "models" / "llama.cpp" / "gguf-py"
if (local_gguf_path / "gguf").exists():
    sys.path.insert(0, str(local_gguf_path))

import numpy as np
import gguf
from gguf.quants import dequantize, quantize, GGML_QUANT_SIZES, _type_traits
from gguf.constants import GGMLQuantizationType

logger = logging.getLogger("requant-tensors")


def quant_type_from_name(name: str) -> GGMLQuantizationType:
    """Resolve a user-facing quant name (e.g. 'q8_0') to a GGMLQuantizationType."""
    try:
        return GGMLQuantizationType[name.upper()]
    except KeyError:
        valid = ", ".join(sorted(t.name for t in GGMLQuantizationType))
        raise SystemExit(
            f"Unknown quantization type '{name}'. Valid names: {valid}"
        )


def is_quantizable(qtype: GGMLQuantizationType) -> bool:
    """True if gguf-py can actually encode (quantize) to this type.

    Some types appear in _type_traits but only implement dequantize_blocks
    (their quantize_blocks raises NotImplementedError), e.g. Q2_K..Q6_K and
    most IQ variants. F32/F16 are special-cased by quantize() itself. We
    prove encode capability by quantizing a single dummy block up front so
    we fail fast with a clear message instead of partway through a model.
    """
    try:
        from gguf.quants import GGML_QUANT_SIZES
        if qtype in (GGMLQuantizationType.F32, GGMLQuantizationType.F16):
            return True
        block_size, _ = GGML_QUANT_SIZES[qtype]
        quantize(np.zeros(block_size, dtype=np.float32), qtype)
        return True
    except NotImplementedError:
        return False
    except Exception:
        return False


def copy_metadata(reader: gguf.GGUFReader, writer: gguf.GGUFWriter) -> None:
    """Copy all key/value metadata from reader to writer (verbatim)."""
    for field in reader.fields.values():
        # Suppress virtual fields and fields written by GGUFWriter itself.
        if field.name == gguf.Keys.General.ARCHITECTURE or field.name.startswith("GGUF."):
            logger.debug(f"Suppressing {field.name}")
            continue
        val = field.contents()
        if val is not None:
            logger.debug(f"Copying metadata {field.name}")
            writer.add_key_value(field.name, val, field.types[0])


def requantized_nbytes(tensor, target_qtype: GGMLQuantizationType) -> int:
    """Exact byte size of `tensor` once requantized to target_qtype."""
    block_size, type_size = GGML_QUANT_SIZES[target_qtype]
    return tensor.n_elements * type_size // block_size


def build_tensor_infos(
    reader: gguf.GGUFReader,
    writer: gguf.GGUFWriter,
    match_qtype: GGMLQuantizationType,
    target_qtype: GGMLQuantizationType,
) -> int:
    """
    Register every tensor with the writer.

    Matched tensors are registered with the target quant type; their payload is
    produced in the write pass. Unmatched tensors are registered verbatim.

    Returns the number of tensors that will be requantized.
    """
    requantize_count = 0
    for tensor in reader.tensors:
        if tensor.tensor_type == match_qtype and match_qtype != target_qtype:
            requantize_count += 1
            nbytes = requantized_nbytes(tensor, target_qtype)
            logger.debug(
                f"Requantize {tensor.name}: {tensor.tensor_type.name} -> {target_qtype.name} "
                f"({tensor.n_bytes} -> {nbytes} bytes)"
            )
            # Logical shape is preserved; dtype tag is the target quant type.
            writer.add_tensor_info(
                tensor.name,
                tensor.shape,
                np.dtype(np.float32),
                nbytes,
                raw_dtype=target_qtype,
            )
        else:
            # Verbatim copy: raw byte shape + uint8 dtype, tagged with the
            # original quant type so the writer stores it unchanged.
            writer.add_tensor_info(
                tensor.name,
                tensor.data.shape,
                tensor.data.dtype,
                tensor.data.nbytes,
                raw_dtype=tensor.tensor_type,
            )
    return requantize_count


def write_tensor_data_pass(
    reader: gguf.GGUFReader,
    writer: gguf.GGUFWriter,
    match_qtype: GGMLQuantizationType,
    target_qtype: GGMLQuantizationType,
    total_bytes: int,
) -> int:
    """Write tensor payloads, requantizing matched tensors on the fly.

    Returns the number of tensors actually requantized.
    """
    bar = tqdm(desc="Writing", total=total_bytes, unit="byte", unit_scale=True)
    processed_requant = 0
    for tensor in reader.tensors:
        if tensor.tensor_type == match_qtype:
            f32 = dequantize(tensor.data, tensor.tensor_type)
            new_data = quantize(f32, target_qtype)
            processed_requant += 1
            logger.debug(
                f"Wrote requantized {tensor.name} ({tensor.n_bytes} -> {new_data.nbytes} bytes)"
            )
            writer.write_tensor_data(new_data)
            bar.update(new_data.nbytes)
        else:
            writer.write_tensor_data(tensor.data)
            bar.update(tensor.n_bytes)
    bar.close()
    return processed_requant


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Requantize only the tensors matching a quant type in a GGUF file, "
        "copying all other tensors verbatim."
    )
    parser.add_argument("input", type=Path, help="Input GGUF file")
    parser.add_argument("output", type=Path, help="Output GGUF file")
    parser.add_argument(
        "--match-quant",
        required=True,
        help="Quantization type of tensors to requantize (e.g. q8_0)",
    )
    parser.add_argument(
        "--target-quant",
        required=True,
        help="Quantization type to convert matched tensors to (e.g. q4_0, f16, bf16)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file without prompting",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    if args.output.exists() and not args.force:
        logger.warning(f'The output file "{args.output}" already exists.')
        response = input("Overwrite? Type YES to proceed: ")
        if response != "YES":
            logger.info("Aborted.")
            sys.exit(0)

    match_qtype = quant_type_from_name(args.match_quant)
    target_qtype = quant_type_from_name(args.target_quant)

    if not is_quantizable(target_qtype):
        # List only targets that genuinely encode (test-encoded up front),
        # not every member of _type_traits (some are dequantize-only).
        encodable = ", ".join(
            sorted(t.name for t in GGMLQuantizationType if is_quantizable(t))
        )
        logger.error(
            f"gguf-py cannot quantize TO {target_qtype.name}. "
            f"Encodable targets: {encodable}"
        )
        sys.exit(1)

    logger.info(f"* Loading: {args.input}")
    reader = gguf.GGUFReader(args.input, "r")

    arch_field = reader.get_field(gguf.Keys.General.ARCHITECTURE)
    arch = arch_field.contents() if arch_field else None
    logger.info(f"Architecture: {arch}")

    alignment_field = reader.get_field(gguf.Keys.General.ALIGNMENT)
    alignment = alignment_field.contents() if alignment_field else None

    logger.info(f"* Writing: {args.output}")
    writer = gguf.GGUFWriter(args.output, arch=arch, endianess=reader.endianess)
    if alignment is not None:
        writer.data_alignment = alignment
        logger.debug(f"Using alignment: {alignment}")

    # Metadata first (writer state: HEADER -> KV_DATA).
    copy_metadata(reader, writer)

    # Tensor info (writer state: KV_DATA -> TI_DATA).
    total_bytes = sum(tensor.n_bytes for tensor in reader.tensors)
    requantize_count = build_tensor_infos(reader, writer, match_qtype, target_qtype)

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()

    # Tensor payloads (writer state: TI_DATA -> WEIGHTS).
    processed_requant = write_tensor_data_pass(
        reader, writer, match_qtype, target_qtype, total_bytes
    )

    writer.close()
    logger.info(
        f"Done: {args.output} "
        f"({processed_requant}/{requantize_count} matched tensors requantized "
        f"to {target_qtype.name}; rest copied verbatim)"
    )


if __name__ == "__main__":
    main()
