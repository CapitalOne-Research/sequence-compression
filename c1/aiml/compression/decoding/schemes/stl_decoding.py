"""Sentinel decoder. See c1/aiml/compression/encoding_schemes.md."""

from typing import TypeVar

T = TypeVar("T", int, float)


def decode(clean_values: list[T], snt_pos: list = None,
           snt_ranges: dict = None, length: int = 0) -> list[T]:
    """Reconstruct the original sequence by reinserting sentinel values.

    Args:
        clean_values: Sequence with sentinels removed.
        snt_pos: Legacy format - list of [position, value] pairs.
        snt_ranges: New compact format - {value: [[start, end], ...]}
        length: Original sequence length.

    Returns:
        Reconstructed original sequence.
    """
    # Handle new compact format
    if snt_ranges:
        # Expand ranges into (position, value) pairs
        pos_val_pairs = []
        for val, ranges in snt_ranges.items():
            val = int(val) if isinstance(val, str) else val  # JSON keys are strings
            for r in ranges:
                if len(r) == 1:
                    pos_val_pairs.append((r[0], val))
                else:
                    for pos in range(r[0], r[1] + 1):
                        pos_val_pairs.append((pos, val))
        
        result = list(clean_values)
        for pos, val in sorted(pos_val_pairs):
            result.insert(pos, val)
        return result[:length]

    # Legacy format support
    if not snt_pos:
        return clean_values

    result = list(clean_values)

    # Insert sentinels back at their original positions (must insert
    # in ascending position order to keep indices correct)
    for pos, val in sorted(snt_pos, key=lambda x: x[0]):
        result.insert(pos, val)

    return result[:length]
