"""Nullmap bit-packing encoder for sparse sequences. See c1/aiml/compression/encoding_schemes.md."""

import base64
import numpy as np

from c1.aiml.compression.utils.bitpack import (
    encode_count,
    encode_signed_varint,
    pack_bits,
)


FLAG_SHORT_COUNT = 0x01
FLAG_ALL_DOMINANT = 0x02


def encode(values: list[int]) -> tuple[str, dict]:
    """Encode a sparse integer sequence using nullmap bit-packing.

    Args:
        values: List of integers to encode.

    Returns:
        Tuple of (base64-encoded string, empty auxiliary info dict).
    """
    if len(values) == 0:
        return "", {}

    values = [int(v) for v in values]
    count = len(values)

    # Find dominant value
    freq: dict = {}
    for v in values:
        freq[v] = freq.get(v, 0) + 1
    dominant = max(freq, key=freq.get)

    count_bytes, is_short = encode_count(count)
    flags = FLAG_SHORT_COUNT if is_short else 0

    header = bytearray([flags])
    header += count_bytes
    header += encode_signed_varint(dominant)

    # Collect non-dominant values
    nz_vals = [v for v in values if v != dominant]

    # All-dominant shortcut
    if not nz_vals:
        header[0] |= FLAG_ALL_DOMINANT
        return base64.b64encode(bytes(header)).decode("utf-8"), {}

    # FOR on non-dominant values
    nz_min = min(nz_vals)
    nz_max = max(nz_vals)
    if nz_min == nz_max:
        bits_per_value = 0
    else:
        adjusted_max = nz_max - nz_min
        bits_per_value = max(1, adjusted_max.bit_length())

    header += bytes([bits_per_value])
    header += encode_signed_varint(nz_min)

    # Nullmap: 1 bit per element, 1 = non-dominant
    nullmap = pack_bits([0 if v == dominant else 1 for v in values], 1)

    # Bit-pack non-dominant values with FOR
    packed = pack_bits([v - nz_min for v in nz_vals], bits_per_value)

    data = bytes(header) + nullmap + packed
    return base64.b64encode(data).decode("utf-8"), {}
