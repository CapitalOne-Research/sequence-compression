def decode(encoded: list[int], stoi: dict[str, int]) -> list[str]:
    """
    Decode a list of integers back to strings.
    
    Args:
        encoded: List of integers to decode.
        stoi: Dictionary mapping strings to integers.
        
    Returns:
        List of strings.
    """
    if len(encoded) == 0:
        return []

    int_to_string = {v: k for k, v in stoi.items()}
    return [int_to_string[i] for i in encoded]

