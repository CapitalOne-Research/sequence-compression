
def encode(sequence: list[int]) -> list[int]:
    """Encode a sequence as run-length pairs.

    Args:
        sequence: Input sequence to encode.

    Returns:
        Flat list alternating between values and their counts.
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