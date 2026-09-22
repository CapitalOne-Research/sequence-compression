from __future__ import annotations


def encode(sequence: list[int]) -> tuple[list[int], dict]:
    """Encode a sequence as run-length pairs.

    Args:
        sequence: Input sequence to encode.

    Returns:
        Tuple of (flat list alternating between values and their counts,
        empty auxiliary info dict).
    """
    if len(sequence) == 0:
        return [], {}

    current_value = sequence[0]
    count = 1

    result = []

    for value in sequence[1:]:
        if value == current_value:
            count += 1
        else:
            result.extend([current_value, count])
            current_value = value
            count = 1

    result.extend([current_value, count])

    return result, {}
