"""Bitmap decoder for binary (0/1) sequences. See c1/aiml/compression/encoding_schemes.md."""

import base64

from c1.aiml.compression.utils.bitpack import unpack_bits


def decode(data: str) -> list[int]:
    """Decode a bitmap string back to a binary (0/1) sequence.

    Args:
        data: Base64-encoded bitmap string.

    Returns:
        List of 0s and 1s.
    """
    if not data:
        return []

    padded = data + "=" * (-len(data) % 4)
    raw = base64.b64decode(padded.encode("utf-8"))

    byte0 = raw[0]
    byte1 = raw[1]

    is_constant = byte1 & 0x01
    count = byte0 | ((byte1 >> 2) << 8)

    if is_constant:
        constant_value = (byte1 >> 1) & 0x01
        return [constant_value] * count

    return unpack_bits(raw[2:], count, 1).tolist()
