"""Tests for the quant (scalar quantization) encoding/decoding pair.

quant is lossy, so we assert reconstructions are within an error tolerance
rather than equal to the original input.
"""

import numpy as np
import pytest

from seqpack.encoding.schemes.quant_encoding import encode
from seqpack.decoding.schemes.quant_decoding import decode


def _max_abs_error(original, reconstructed):
    return float(np.max(np.abs(np.array(original) - np.array(reconstructed))))


class TestQuantRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == []
        assert decode(encoded, **aux) == []

    def test_constant_sequence_uses_scale_zero(self):
        values = [3.14] * 8
        encoded, aux = encode(values)
        assert aux["q_scale"] == 0.0
        assert decode(encoded, **aux) == [3.14] * 8

    def test_asymmetric_for_positive_range(self):
        values = list(np.linspace(10.0, 20.0, 32))
        encoded, aux = encode(values, num_bits=8)
        assert aux["q_sym"] == 0
        decoded = decode(encoded, **aux)
        # 1 LSB error: scale = (20-10)/255 ~= 0.0392
        assert _max_abs_error(values, decoded) <= aux["q_scale"]

    def test_symmetric_for_zero_centered_range(self):
        values = list(np.linspace(-1.0, 1.0, 32))
        encoded, aux = encode(values, num_bits=8)
        assert aux["q_sym"] == 1
        decoded = decode(encoded, **aux)
        assert _max_abs_error(values, decoded) <= aux["q_scale"]

    def test_more_bits_means_lower_error(self):
        values = list(np.linspace(0.0, 100.0, 64))
        _, aux_low = encode(values, num_bits=4)
        _, aux_high = encode(values, num_bits=12)
        # Scale should be smaller with more bits, indicating finer resolution
        assert aux_high["q_scale"] < aux_low["q_scale"]

    def test_quantized_values_within_range(self):
        values = list(np.linspace(0.0, 50.0, 16))
        encoded, aux = encode(values, num_bits=8)
        max_q = (1 << aux["q_bits"]) - 1
        assert min(encoded) >= 0
        assert max(encoded) <= max_q

    def test_num_bits_zero_raises_value_error(self):
        with pytest.raises(ValueError, match="num_bits must be between 1 and 16"):
            encode([1.0, 2.0, 3.0], num_bits=0)

    def test_num_bits_too_large_raises_value_error(self):
        with pytest.raises(ValueError, match="num_bits must be between 1 and 16"):
            encode([1.0, 2.0, 3.0], num_bits=64)

    def test_num_bits_one_on_symmetric_data_does_not_divide_by_zero(self):
        # Zero-centered data triggers the symmetric path, whose offset is
        # (1 << (num_bits - 1)) - 1 -- which is 0 at num_bits=1 and used to
        # raise ZeroDivisionError. num_bits=1 must fall back to asymmetric.
        values = [1.0, -1.0, 0.5, -0.5]
        encoded, aux = encode(values, num_bits=1)
        assert aux["q_sym"] == 0
        decoded = decode(encoded, **aux)
        assert _max_abs_error(values, decoded) <= aux["q_scale"]
