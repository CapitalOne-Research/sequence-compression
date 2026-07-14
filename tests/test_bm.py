"""Tests for the bm (bitmap) encoding/decoding pair."""

from c1.aiml.compression.encoding.schemes.bm_encoding import encode
from c1.aiml.compression.decoding.schemes.bm_decoding import decode


class TestBmRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == ""
        assert aux == {}
        assert decode(encoded) == []

    def test_constant_zeros(self):
        values = [0] * 50
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_constant_ones(self):
        values = [1] * 12
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_mixed_pattern(self):
        values = [1, 0, 1, 1, 0, 0, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1]
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_single_element(self):
        for v in [0, 1]:
            encoded, _ = encode([v])
            assert decode(encoded) == [v]

    def test_max_supported_length(self):
        values = [(i % 2) for i in range(16383)]
        encoded, _ = encode(values)
        assert decode(encoded) == values

    def test_constant_payload_is_smaller_than_mixed(self):
        constant_encoded, _ = encode([1] * 100)
        mixed_encoded, _ = encode([1, 0] * 50)
        assert len(constant_encoded) < len(mixed_encoded)
