"""Tests for the bp (bit-packing) encoding/decoding pair."""

import pytest

from seqpack.encoding.schemes.bp_encoding import encode
from seqpack.decoding.schemes.bp_decoding import decode


class TestBpRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == ""
        assert aux == {}
        assert decode(encoded) == []

    def test_constant_sequence(self):
        values = [42] * 10
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_small_unsigned_range(self):
        values = [0, 1, 2, 3, 0, 1, 2, 3] * 5
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_signed_values_use_for(self):
        values = [-5, -3, 0, 7, 10, 15]
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_large_values(self):
        values = [1000, 2000, 3000, 4000, 5000]
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_long_sequence_uses_long_count_path(self):
        values = list(range(70_000))
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_explicit_bits_per_value(self):
        values = [0, 1, 2, 3]
        encoded, _ = encode(values, bits_per_value=4)
        assert decode(encoded) == values

    def test_value_requiring_64_bits_raises_instead_of_corrupting(self):
        # Previously this silently sign-flipped to a negative number instead
        # of raising -- a value needing 64 bits after FOR subtraction.
        with pytest.raises(ValueError, match="between 0 and 63"):
            encode([0, 2**63 + 1, 5])
