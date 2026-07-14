"""Bit-packing encoder. See c1/aiml/compression/encoding_schemes.md."""

import base64
from typing import TypeVar

from c1.aiml.compression.utils.bitpack import (
    encode_count,
    encode_signed_varint,
    pack_bits,
)

T = TypeVar("T", bound=int)

# Header flag bits
FLAG_HAS_ZIGZAG = 0x01    # Bit 0: zigzag encoding was applied
FLAG_HAS_FOR = 0x02       # Bit 1: frame-of-reference encoding (min stored in header)
FLAG_IS_CONSTANT = 0x04   # Bit 2: constant sequence (single value, no payload)
FLAG_SHORT_COUNT = 0x08   # Bit 3: count field is 2 bytes (otherwise 4 bytes)


def encode(values: list[int], bits_per_value: int | None = None) -> (str, dict):
    """Encode a list of integers using bit packing.

    Args:
        values: List of integers to encode.
        bits_per_value: Bits per value. If None, calculated from the data range.

    Returns:
        Tuple of (base64-encoded packed string, empty auxiliary info dict).
    """
    if len(values) == 0:
        return "", {}

    values = [int(v) for v in values]

    count = len(values)
    min_val = min(values)
    max_val = max(values)

    count_bytes, is_short = encode_count(count)
    flags = FLAG_SHORT_COUNT if is_short else 0

    # Constant sequence: store only the single value, no payload
    if min_val == max_val:
        flags |= FLAG_IS_CONSTANT
        header = bytes([0, flags]) + count_bytes + encode_signed_varint(min_val)
        return base64.b64encode(header).decode("utf-8"), {}

    # Frame-of-reference: subtract min to reduce value range
    if min_val != 0:
        flags |= FLAG_HAS_FOR
        adjusted = [v - min_val for v in values]
    else:
        adjusted = values

    # After FOR subtraction all values are >= 0, so zigzag is unnecessary.
    pack_values = adjusted

    # Calculate bits needed if not specified
    if bits_per_value is None:
        max_pack_val = int(max(pack_values))
        bits_per_value = max(1, max_pack_val.bit_length())

    # Build header: [bits_per_value][flags][count][optional FOR min]
    header = bytes([bits_per_value, flags]) + count_bytes
    if flags & FLAG_HAS_FOR:
        header += encode_signed_varint(min_val)

    data = header + pack_bits(pack_values, bits_per_value)
    return base64.b64encode(data).decode("utf-8"), {}
