"""Bitmap encoder for binary (0/1) sequences. See seqpack/encoding_schemes.md."""

from __future__ import annotations

import base64

from seqpack.utils.bitpack import pack_bits

# The count field is packed into 14 bits alongside the header's flag/min-value
# bits (see byte1 below), so counts above this cannot be represented.
BM_MAX_COUNT = 16383


def encode(values: list[int]) -> tuple[str, dict]:
    """Encode a binary (0/1) sequence into a compact bitmap string.

    Args:
        values: List of 0s and 1s to encode. Length must be <= BM_MAX_COUNT.

    Raises:
        ValueError: If `values` is longer than BM_MAX_COUNT.

    Returns:
        Tuple of (base64-encoded bitmap string, empty auxiliary info dict).
    """
    count = len(values)
    if count == 0:
        return "", {}
    if count > BM_MAX_COUNT:
        raise ValueError(f"bm supports at most {BM_MAX_COUNT} values, got {count}")

    values = [int(v) for v in values]
    min_val = min(values)
    max_val = max(values)

    # Constant sequence: 2-byte header only, no payload
    if min_val == max_val:
        byte0 = count & 0xFF
        byte1 = ((count >> 8) << 2) | (min_val << 1) | 0x01
        return base64.b64encode(bytes([byte0, byte1])).decode("utf-8"), {}

    # Non-constant: 2-byte header + bitmap payload
    byte0 = count & 0xFF
    byte1 = ((count >> 8) << 2) | 0x00  # constant=0
    header = bytes([byte0, byte1])
    return base64.b64encode(header + pack_bits(values, 1)).decode("utf-8"), {}

