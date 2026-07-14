"""Delta encoder — replaces values with consecutive differences. See c1/aiml/compression/encoding_schemes.md."""

from typing import TypeVar
import numpy as np

T = TypeVar("T", int, float)

def encode(values: list[T]) -> tuple[list[int], dict]:
    """Encode a sequence using delta encoding."""
    if len(values) == 0:
        return [], {}

    # Calculate deltas (excluding first value, stored in auxiliary info)
    deltas = [values[i] - values[i-1] for i in range(1, len(values))]
    
    return deltas, {"v0": values[0]}
