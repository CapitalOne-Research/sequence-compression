"""Sentinel decoder. See seqpack/encoding_schemes.md."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T", int, float)


def _parse_sentinel_key(key: str) -> int | float:
    """Parse a JSON dict key back into the numeric sentinel value it names."""
    try:
        return int(key)
    except ValueError:
        return float(key)


def decode(clean_values: list[T], snt_pos: list = None,
           snt_ranges: dict = None, length: int = 0) -> list[T]:
    """Reconstruct the original sequence by reinserting sentinel values.

    Args:
        clean_values: Sequence with sentinels removed.
        snt_pos: Active format for the no-sentinel case (always ``[]``) —
            list of [position, value] pairs.
        snt_ranges: Compact format used when sentinels were found —
            {value: [[start, end], ...]}
        length: Original sequence length.

    Returns:
        Reconstructed original sequence.
    """
    # Handle new compact format
    if snt_ranges:
        # Expand ranges into (position, value) pairs
        pos_val_pairs = []
        for val, ranges in snt_ranges.items():
            val = _parse_sentinel_key(val) if isinstance(val, str) else val
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

    # No-sentinel case: snt_pos is always [] on this path.
    if not snt_pos:
        return clean_values

    result = list(clean_values)

    # Insert sentinels back at their original positions (must insert
    # in ascending position order to keep indices correct)
    for pos, val in sorted(snt_pos, key=lambda x: x[0]):
        result.insert(pos, val)

    return result[:length]
