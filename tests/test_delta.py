"""Tests for the del (delta) encoding/decoding pair."""

from c1.aiml.compression.encoding.schemes.delta_encoding import encode
from c1.aiml.compression.decoding.schemes.delta_decoding import decode


class TestDeltaRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == []
        assert aux == {}

    def test_single_element_emits_v0_only(self):
        encoded, aux = encode([42])
        assert encoded == []
        assert aux == {"v0": 42}
        assert decode(encoded, **aux) == [42]

    def test_monotonic_sequence(self):
        values = [10, 11, 13, 16, 20]
        encoded, aux = encode(values)
        assert encoded == [1, 2, 3, 4]
        assert aux == {"v0": 10}
        assert decode(encoded, **aux) == values

    def test_includes_negative_deltas(self):
        values = [10, 5, 7, 3]
        encoded, aux = encode(values)
        assert encoded == [-5, 2, -4]
        assert decode(encoded, **aux) == values

    def test_constant_sequence_yields_zero_deltas(self):
        values = [7, 7, 7, 7]
        encoded, aux = encode(values)
        assert encoded == [0, 0, 0]
        assert decode(encoded, **aux) == values
