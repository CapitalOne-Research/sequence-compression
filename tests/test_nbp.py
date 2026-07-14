"""Tests for the nbp (nullmap bit-packing) encoding/decoding pair."""

from c1.aiml.compression.encoding.schemes.nbp_encoding import encode
from c1.aiml.compression.decoding.schemes.nbp_decoding import decode


class TestNbpRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == ""
        assert aux == {}
        assert decode(encoded) == []

    def test_all_dominant_value(self):
        values = [3] * 20
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_sparse_with_one_dominant(self):
        values = [0] * 30 + [5, 7, 9] + [0] * 10
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_two_distinct_non_dominant_values(self):
        values = [1, 1, 1, 2, 1, 1, 3, 1, 1]
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_long_sequence_uses_long_count(self):
        values = ([0] * 100 + [9]) * 700  # > 65535 elements
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_negative_dominant(self):
        values = [-5, -5, -5, 1, -5, -5, 0]
        encoded, _ = encode(values)
        assert decode(encoded) == values
