"""Binary packing helpers shared across bp, nbp, and bitmap schemes.

Covers two concerns:
  * varint (LEB128) and zigzag-signed varint encode/decode for header fields.
  * fixed-width bit packing/unpacking of unsigned integers, with the byte
    stream zero-padded to a multiple of 8 bits.

`encode_count` / `decode_count` capture the 2-or-4-byte count field that
both bp and nbp store after their flag byte.
"""

from __future__ import annotations

import numpy as np


def encode_varint(n: int) -> bytes:
    """Encode an unsigned integer as a varint (LEB128)."""
    result = bytearray()
    while n > 0x7F:
        result.append((n & 0x7F) | 0x80)
        n >>= 7
    result.append(n & 0x7F)
    return bytes(result)


def encode_signed_varint(n: int) -> bytes:
    """Encode a signed integer as a zigzag varint."""
    unsigned = (n << 1) ^ (n >> 63) if n < 0 else n << 1
    return encode_varint(unsigned)


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a varint (LEB128), returning (value, bytes_consumed)."""
    result = 0
    shift = 0
    consumed = 0
    while True:
        byte = data[offset + consumed]
        result |= (byte & 0x7F) << shift
        consumed += 1
        if not (byte & 0x80):
            break
        shift += 7
    return result, consumed


def decode_signed_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a zigzag varint, returning (value, bytes_consumed)."""
    unsigned, consumed = decode_varint(data, offset)
    value = (unsigned >> 1) ^ -(unsigned & 1)
    return value, consumed


def encode_count(count: int) -> tuple[bytes, bool]:
    """Encode `count` as 2 bytes when it fits in 16 bits, otherwise 4.

    Returns (count_bytes, is_short) so the caller can record the choice in
    its scheme-specific flag bit.
    """
    if count <= 0xFFFF:
        return count.to_bytes(2, "big"), True
    return count.to_bytes(4, "big"), False


def decode_count(data: bytes, offset: int, is_short: bool) -> tuple[int, int]:
    """Decode a count written by `encode_count`, returning (count, bytes_consumed)."""
    width = 2 if is_short else 4
    return int.from_bytes(data[offset:offset + width], "big"), width


def pack_bits(values, bits_per_value: int) -> bytes:
    """Pack unsigned integers into bytes at `bits_per_value` bits each (MSB first).

    The bit stream is zero-padded to a multiple of 8 bits before being packed
    into bytes.

    Raises:
        ValueError: If `bits_per_value` is outside [0, 63]. 64 is excluded
            because `unpack_bits` reconstructs values with signed int64
            weights, and a weight of 1 << 63 overflows to a negative number.
    """
    if not 0 <= bits_per_value <= 63:
        raise ValueError(f"bits_per_value must be between 0 and 63, got {bits_per_value}")
    if bits_per_value == 0 or len(values) == 0:
        return b""

    arr = np.asarray(values, dtype=np.uint64)
    arr = arr & ((1 << bits_per_value) - 1)

    shifts = np.arange(bits_per_value - 1, -1, -1, dtype=np.uint64)
    bits = ((arr[:, np.newaxis] >> shifts) & 1).ravel().astype(np.uint8)

    pad = (-len(bits)) % 8
    if pad:
        bits = np.pad(bits, (0, pad))

    return np.packbits(bits).tobytes()


def unpack_bits(data: bytes, count: int, bits_per_value: int) -> np.ndarray:
    """Inverse of `pack_bits`: return a length-`count` int64 array.

    Reads only the bytes needed (`ceil(count * bits_per_value / 8)`); if
    `data` is shorter than that, the missing bits are treated as zero.

    Raises:
        ValueError: If `bits_per_value` is outside [0, 63] (see `pack_bits`).
    """
    if not 0 <= bits_per_value <= 63:
        raise ValueError(f"bits_per_value must be between 0 and 63, got {bits_per_value}")
    if count == 0 or bits_per_value == 0:
        return np.zeros(count, dtype=np.int64)

    total_bits = count * bits_per_value
    needed_bytes = (total_bits + 7) // 8
    byte_arr = np.frombuffer(data[:needed_bytes], dtype=np.uint8)
    bits = np.unpackbits(byte_arr)

    if len(bits) < total_bits:
        bits = np.pad(bits, (0, total_bits - len(bits)))
    else:
        bits = bits[:total_bits]

    bits_2d = bits.reshape(count, bits_per_value).astype(np.int64)
    weights = 1 << np.arange(bits_per_value - 1, -1, -1, dtype=np.int64)
    return bits_2d @ weights
