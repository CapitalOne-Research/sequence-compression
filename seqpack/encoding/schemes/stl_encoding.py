"""Sentinel encoder — strips outlier values to narrow the value range. See seqpack/encoding_schemes.md."""

from typing import TypeVar

T = TypeVar("T", int, float)


def encode(values: list[T], iqr_factor: float = 3.0) -> tuple[list[T], dict]:
    """Strip outlier sentinel values from a numeric sequence.

    Args:
        values: Numeric sequence that may contain sentinel/null outliers.
        iqr_factor: Multiplier for the IQR fence; values beyond
            ``median ± iqr_factor * IQR`` are classified as sentinels.

    Returns:
        Tuple of (clean_values, auxiliary_info).
    """
    n = len(values)
    if n <= 2:
        return values, {"snt_pos": [], "length": n}

    # Sort once to get quartiles
    sorted_vals = sorted(values)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1

    if iqr == 0:
        # Nearly constant — use median ± small absolute tolerance
        median = sorted_vals[n // 2]
        lo = median - 1
        hi = median + 1
    else:
        median = sorted_vals[n // 2]
        fence = iqr_factor * iqr
        lo = median - fence
        hi = median + fence

    # Collect sentinel positions grouped by value
    sentinel_by_value: dict[T, list[int]] = {}
    clean = []
    for i, v in enumerate(values):
        if v < lo or v > hi:
            sentinel_by_value.setdefault(v, []).append(i)
        else:
            clean.append(v)

    # If no sentinels found, return original unchanged
    if not sentinel_by_value:
        return values, {"snt_pos": [], "length": n}

    # Compress positions into ranges for each sentinel value
    # Format: {value: [[start, end], [start, end], ...]} where end is inclusive
    # Keys are strings for JSON compatibility
    snt_ranges: dict[str, list] = {}
    for val, positions in sentinel_by_value.items():
        ranges = []
        start = positions[0]
        end = start
        for pos in positions[1:]:
            if pos == end + 1:
                end = pos
            else:
                ranges.append([start, end] if start != end else [start])
                start = pos
                end = pos
        ranges.append([start, end] if start != end else [start])
        snt_ranges[str(val)] = ranges

    return clean, {"snt_ranges": snt_ranges, "length": n}
