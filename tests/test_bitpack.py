"""Tests for seqpack.utils.bitpack."""

import numpy as np
import pytest

from seqpack.utils.bitpack import (
    decode_count,
    decode_signed_varint,
    decode_varint,
    encode_count,
    encode_signed_varint,
    encode_varint,
    pack_bits,
    unpack_bits,
)


class TestVarint:
    @pytest.mark.parametrize("n", [0, 1, 42, 127])
    def test_round_trip_small(self, n):
        data = encode_varint(n)
        value, consumed = decode_varint(data, 0)
        assert value == n
        assert consumed == len(data)

    @pytest.mark.parametrize("n", [128, 16383, 16384, 1 << 30])
    def test_round_trip_multibyte(self, n):
        data = encode_varint(n)
        value, consumed = decode_varint(data, 0)
        assert value == n
        assert consumed == len(data)

    def test_offset_in_buffer(self):
        prefix = b"\xff\xff"
        payload = encode_varint(300)
        value, consumed = decode_varint(prefix + payload, len(prefix))
        assert value == 300
        assert consumed == len(payload)


class TestSignedVarint:
    @pytest.mark.parametrize("n", [-1 << 30, -1, 0, 1, 1 << 30])
    def test_round_trip(self, n):
        data = encode_signed_varint(n)
        value, _ = decode_signed_varint(data, 0)
        assert value == n


class TestEncodeCount:
    def test_short_count(self):
        b, is_short = encode_count(100)
        assert is_short is True
        assert len(b) == 2

    def test_at_short_boundary(self):
        b, is_short = encode_count(0xFFFF)
        assert is_short is True
        assert len(b) == 2

    def test_long_count(self):
        b, is_short = encode_count(0xFFFF + 1)
        assert is_short is False
        assert len(b) == 4

    def test_round_trip_short(self):
        b, is_short = encode_count(1234)
        count, consumed = decode_count(b, 0, is_short)
        assert count == 1234
        assert consumed == 2

    def test_round_trip_long(self):
        b, is_short = encode_count(1_000_000)
        count, consumed = decode_count(b, 0, is_short)
        assert count == 1_000_000
        assert consumed == 4


class TestPackBits:
    def test_round_trip_simple(self):
        values = [1, 0, 1, 1, 0, 0, 1, 0]
        packed = pack_bits(values, 1)
        result = unpack_bits(packed, len(values), 1).tolist()
        assert result == values

    def test_round_trip_multibit(self):
        values = [0, 1, 2, 3, 4, 5, 6, 7]
        packed = pack_bits(values, 3)
        result = unpack_bits(packed, len(values), 3).tolist()
        assert result == values

    def test_zero_bits_returns_empty(self):
        assert pack_bits([1, 2, 3], 0) == b""

    def test_empty_input(self):
        assert pack_bits([], 4) == b""

    def test_unpack_pads_when_data_is_short(self):
        # Asking for more bits than the data carries should zero-fill
        result = unpack_bits(b"", 5, 3)
        assert result.tolist() == [0, 0, 0, 0, 0]

    def test_pack_truncates_to_bit_width(self):
        # Values larger than 2**bits-1 are masked, not error
        packed = pack_bits([0b101], 2)
        result = unpack_bits(packed, 1, 2).tolist()
        assert result == [0b01]

    def test_bits_per_value_63_round_trips(self):
        values = [0, 2**62, 5]
        packed = pack_bits(values, 63)
        assert unpack_bits(packed, len(values), 63).tolist() == values

    def test_pack_bits_rejects_width_64(self):
        # Width 64 would need a weight of 1 << 63, which overflows int64 to
        # a negative number and silently sign-flips the result on unpack.
        with pytest.raises(ValueError, match="between 0 and 63"):
            pack_bits([0, 1, 2], 64)

    def test_unpack_bits_rejects_width_64(self):
        with pytest.raises(ValueError, match="between 0 and 63"):
            unpack_bits(b"", 3, 64)
