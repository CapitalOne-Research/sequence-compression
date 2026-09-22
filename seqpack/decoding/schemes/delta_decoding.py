"""Delta decoder. See seqpack/encoding_schemes.md."""

from __future__ import annotations

from typing import TypeVar

import numpy as np

T = TypeVar("T", int, float)


def decode(deltas: list[T], v0: T | None = None) -> list[T]:
    """Decode a sequence using delta encoding.

    Accumulates exactly in Python ints when every value is an int, avoiding
    both float rounding and int64 overflow. Falls back to float64 as soon as
    any value is a float, since `deltas`/`v0` are float whenever the
    original sequence was.

    `v0` defaults to None, not 0: `encode()` omits `v0` from its aux dict
    only when the original input was empty, so an absent `v0` unambiguously
    means "decode to an empty list" -- as opposed to a single-element input
    of `0`, which always carries an explicit `v0=0`.

    Note: for float input, `v0 + (v1 - v0)` is not guaranteed to be bit-exact
    with `v1` -- this is a property of IEEE 754 arithmetic, not this
    implementation. Reconstruction is exact to within a few ULP, not always
    exact to the bit. Round-trip precision decreases with more elements and
    with larger value magnitudes.
    """
    if v0 is None:
        return []
    values = [v0, *deltas]
    if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        result = []
        total = 0
        for v in values:
            total += v
            result.append(total)
        return result
    return np.cumsum(np.asarray(values, dtype=np.float64)).tolist()
