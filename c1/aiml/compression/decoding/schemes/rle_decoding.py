
def decode(encoded: list[int]) -> list[int]:
    """Decode run-length pairs back to the original sequence.

    Args:
        encoded: List of run-length pairs (flat / tuple / dict format).

    Returns:
        Decoded sequence.
    """
    result = []
    if len(encoded) == 0:
        return result

    for i in range(0, len(encoded), 2):
        value = encoded[i]
        count = encoded[i + 1]
        result.extend([value] * count)

    return result