"""Delta encoder — replaces values with consecutive differences. See seqpack/encoding_schemes.md."""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T", int, float)


def encode(values: list[T]) -> tuple[list[T], dict]:
    """Encode a sequence using delta encoding."""
    if len(values) == 0:
        return [], {}

    # Calculate deltas (excluding first value, stored in auxiliary info)
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]

    return deltas, {"v0": values[0]}
