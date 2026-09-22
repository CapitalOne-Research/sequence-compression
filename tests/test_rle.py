"""Tests for the rle (run-length encoding) encoding/decoding pair."""

import pytest

from seqpack.encoding.schemes.rle_encoding import encode
from seqpack.decoding.schemes.rle_decoding import decode


class TestRleRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == []
        assert aux == {}
        assert decode(encoded) == []

    def test_long_runs(self):
        values = [1] * 5 + [2] * 3 + [3] * 4
        encoded, _ = encode(values)
        assert encoded == [1, 5, 2, 3, 3, 4]
        assert decode(encoded) == values

    def test_no_runs(self):
        values = [1, 2, 3, 4, 5]
        encoded, _ = encode(values)
        assert encoded == [1, 1, 2, 1, 3, 1, 4, 1, 5, 1]
        assert decode(encoded) == values

    def test_single_value(self):
        encoded, _ = encode([7])
        assert encoded == [7, 1]
        assert decode(encoded) == [7]

    def test_strings(self):
        values = ["a", "a", "b", "b", "b"]
        encoded, _ = encode(values)
        assert encoded == ["a", 2, "b", 3]
        assert decode(encoded) == values

    def test_odd_length_raises_value_error(self):
        with pytest.raises(ValueError, match="even length"):
            decode([1, 2, 3])
