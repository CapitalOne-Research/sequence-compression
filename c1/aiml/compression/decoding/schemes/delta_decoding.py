"""Delta decoder. See c1/aiml/compression/encoding_schemes.md."""

from typing import TypeVar
import numpy as np

T = TypeVar("T", int, float)

def decode(deltas: list[int], v0: int = 0) -> list[T]:
    """Decode a sequence using delta encoding."""
    arr = np.array([v0] + deltas, dtype=np.int64)
    return np.cumsum(arr).tolist()
