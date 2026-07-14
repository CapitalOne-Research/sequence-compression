"""Nullmap bit-packing decoder. See c1/aiml/compression/encoding_schemes.md."""

import base64
import numpy as np

from c1.aiml.compression.utils.bitpack import (
    decode_count,
    decode_signed_varint,
    unpack_bits,
)


FLAG_SHORT_COUNT = 0x01
FLAG_ALL_DOMINANT = 0x02


def decode(data: str) -> list[int]:
    """Decode a nullmap bit-packed string back to the original sequence.

    Args:
        data: Base64-encoded string from encode().

    Returns:
        List of integers.
    """
    if not data:
        return []

    raw = base64.b64decode(data.encode("utf-8"))
    offset = 0

    flags = raw[offset]
    offset += 1

    count, consumed = decode_count(raw, offset, bool(flags & FLAG_SHORT_COUNT))
    offset += consumed

    # Read dominant
    dominant, consumed = decode_signed_varint(raw, offset)
    offset += consumed

    # All-dominant shortcut
    if flags & FLAG_ALL_DOMINANT:
        return [dominant] * count

    # Read bits_per_value and FOR min
    bits_per_value = raw[offset]
    offset += 1
    for_min, consumed = decode_signed_varint(raw, offset)
    offset += consumed

    # Read nullmap (1 bit per element)
    nullmap_bytes = (count + 7) // 8
    nullmap = unpack_bits(raw[offset:offset + nullmap_bytes], count, 1)
    offset += nullmap_bytes

    nz_count = int(nullmap.sum())

    # Read packed non-dominant values
    if bits_per_value == 0:
        nz_values = np.full(nz_count, for_min, dtype=np.int64)
    else:
        packed_bytes = (nz_count * bits_per_value + 7) // 8
        nz_values = unpack_bits(raw[offset:offset + packed_bytes], nz_count, bits_per_value) + for_min

    # Reconstruct
    result = np.full(count, dominant, dtype=np.int64)
    result[nullmap.astype(bool)] = nz_values
    return result.tolist()
