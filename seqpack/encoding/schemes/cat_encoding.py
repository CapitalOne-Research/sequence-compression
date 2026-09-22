from __future__ import annotations


def encode(values: list[str], frequency_sorted: bool = True) -> tuple[list[int], dict[str, dict[str, int]]]:
    """Encode a list of strings to integers.

    Args:
        values: List of strings to encode.
        frequency_sorted: If True, assign smallest ints to most frequent values.

    Returns:
        Tuple of (list of int ids, auxiliary info dict with `stoi` map).
    """
    if len(values) == 0:
        return [], {"stoi": {}}

    if frequency_sorted:
        # Count frequencies and assign smallest ints to most frequent values
        freq: dict[str, int] = {}
        for s in values:
            freq[s] = freq.get(s, 0) + 1
        # Sort by frequency descending, then alphabetically for stability
        sorted_keys = sorted(freq, key=lambda k: (-freq[k], k))
        string_to_int = {k: i for i, k in enumerate(sorted_keys)}
    else:
        # Original first-appearance order
        string_to_int = {}
        for s in values:
            if s not in string_to_int:
                string_to_int[s] = len(string_to_int)

    encoded = [string_to_int[s] for s in values]
    return encoded, {"stoi": string_to_int}
