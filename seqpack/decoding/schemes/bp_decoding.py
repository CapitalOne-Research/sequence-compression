"""Bit-packing decoder. See seqpack/encoding_schemes.md."""

from __future__ import annotations

import base64

from seqpack.utils.bitpack import (
    decode_count,
    decode_signed_varint,
    unpack_bits,
)

# Header flag bits
FLAG_HAS_ZIGZAG = 0x01    # Bit 0: zigzag encoding was applied
FLAG_HAS_FOR = 0x02       # Bit 1: frame-of-reference encoding (min stored in header)
FLAG_IS_CONSTANT = 0x04   # Bit 2: constant sequence (single value, no payload)
FLAG_SHORT_COUNT = 0x08   # Bit 3: count field is 2 bytes (otherwise 4 bytes)


def decode(data_w_header: str) -> list[int]:
    """Decode a bit-packed string back to a list of integers.

    Args:
        data_w_header: Base64-encoded bit-packed string with header.

    Returns:
        List of decoded signed integers.
    """
    data = base64.b64decode(data_w_header.encode("utf-8"))
    if not data:
        return []

    bits_per_value = data[0]
    flags = data[1]
    offset = 2

    count, consumed = decode_count(data, offset, bool(flags & FLAG_SHORT_COUNT))
    offset += consumed

    if count == 0:
        return []

    # Constant sequence: read single value and replicate
    if flags & FLAG_IS_CONSTANT:
        value, _ = decode_signed_varint(data, offset)
        return [value] * count

    # Read FOR min value if present
    for_min = 0
    if flags & FLAG_HAS_FOR:
        for_min, consumed = decode_signed_varint(data, offset)
        offset += consumed

    unsigned = unpack_bits(data[offset:], count, bits_per_value)

    # Apply zigzag decode if flag is set
    if flags & FLAG_HAS_ZIGZAG:
        unsigned = (unsigned >> 1) ^ -(unsigned & 1)

    if for_min != 0:
        unsigned = unsigned + for_min

    return unsigned.tolist()
