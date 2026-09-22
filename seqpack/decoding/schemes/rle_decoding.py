from __future__ import annotations


def decode(encoded: list[int]) -> list[int]:
    """Decode run-length pairs back to the original sequence.

    Args:
        encoded: Flat list alternating value, count, value, count, ...

    Raises:
        ValueError: If `encoded` has an odd length (a value with no
            matching count).

    Returns:
        Decoded sequence.
    """
    if len(encoded) % 2 != 0:
        raise ValueError(
            f"rle-encoded data must have an even length (value, count pairs); got {len(encoded)}"
        )

    result = []
    if len(encoded) == 0:
        return result

    for i in range(0, len(encoded), 2):
        value = encoded[i]
        count = encoded[i + 1]
        result.extend([value] * count)

    return result
