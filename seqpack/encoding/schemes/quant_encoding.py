"""Scalar quantization encoder (lossy). See seqpack/encoding_schemes.md."""

from __future__ import annotations

import numpy as np


def encode(values: list[float], num_bits: int = 16) -> tuple[list[int], dict]:
    """Quantize floats to unsigned integers for downstream compression.

    Args:
        values: List of float values to quantize.
        num_bits: Bits per quantized value (1-16). Default 16.

    Raises:
        ValueError: If `num_bits` is not in [1, 16].

    Returns:
        Tuple of (quantized integers in [0, 2^num_bits - 1], auxiliary info dict).
    """
    if num_bits < 1 or num_bits > 16:
        raise ValueError("num_bits must be between 1 and 16")
    if len(values) == 0:
        return [], {}

    arr = np.array(values, dtype=np.float64)
    min_val = float(arr.min())
    max_val = float(arr.max())

    # Constant sequence: scale=0 signals this to decode
    if min_val == max_val:
        return [0] * len(values), {
            "q_scale": 0.0,
            "q_zp": min_val,
            "q_bits": num_bits,
            "q_sym": 0,
        }

    # Auto-detect: symmetric if data is roughly centered around zero.
    # num_bits=1 can't be represented symmetrically (offset would be 0 and
    # divide by zero below), so always fall back to asymmetric there.
    data_range = max_val - min_val
    if num_bits > 1 and abs(min_val + max_val) < 0.1 * data_range:
        return _encode_symmetric(arr, min_val, max_val, num_bits)
    return _encode_asymmetric(arr, min_val, max_val, num_bits)


def _encode_asymmetric(
    arr: np.ndarray, min_val: float, max_val: float, num_bits: int
) -> tuple[list[int], dict]:
    max_q = (1 << num_bits) - 1
    scale = (max_val - min_val) / max_q

    quantized = np.round((arr - min_val) / scale).astype(np.int64)
    np.clip(quantized, 0, max_q, out=quantized)

    return quantized.tolist(), {
        "q_scale": scale,
        "q_zp": min_val,
        "q_bits": num_bits,
        "q_sym": 0,
    }


def _encode_symmetric(
    arr: np.ndarray, min_val: float, max_val: float, num_bits: int
) -> tuple[list[int], dict]:
    abs_max = max(abs(min_val), abs(max_val))
    offset = (1 << (num_bits - 1)) - 1
    scale = abs_max / offset

    quantized = np.round(arr / scale).astype(np.int64) + offset
    np.clip(quantized, 0, 2 * offset, out=quantized)

    return quantized.tolist(), {
        "q_scale": scale,
        "q_zp": 0.0,
        "q_bits": num_bits,
        "q_sym": 1,
    }
