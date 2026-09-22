"""Scalar quantization decoder. See seqpack/encoding_schemes.md."""

import numpy as np

def decode(
    quantized: list[int],
    q_scale: float = 1.0,
    q_zp: float = 0.0,
    q_bits: int = 16,
    q_sym: int = 0,
) -> list[float]:
    """Dequantize integers back to floats.

    Args:
        quantized: List of quantized integers.
        q_scale: Quantization step size.
        q_zp: Zero point (min_val for asymmetric, 0.0 for symmetric).
        q_bits: Number of quantization bits.
        q_sym: 1 for symmetric mode, 0 for asymmetric.

    Returns:
        List of reconstructed float values.
    """
    if len(quantized) == 0:
        return []

    arr = np.array(quantized, dtype=np.float64)

    # Constant case
    if q_scale == 0.0:
        return [q_zp] * len(quantized)

    if q_sym:
        offset = (1 << (q_bits - 1)) - 1
        result = (arr - offset) * q_scale
    else:
        result = arr * q_scale + q_zp

    return result.tolist()
