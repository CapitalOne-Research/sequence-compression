"""Bitmap encoder for binary (0/1) sequences. See c1/aiml/compression/encoding_schemes.md."""

import base64

from c1.aiml.compression.utils.bitpack import pack_bits


def encode(values: list[int]) -> tuple[str, dict]:
    """Encode a binary (0/1) sequence into a compact bitmap string.

    Args:
        values: List of 0s and 1s to encode.

    Returns:
        Tuple of (base64-encoded bitmap string, empty auxiliary info dict).
    """
    count = len(values)
    if count == 0:
        return "", {}

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
