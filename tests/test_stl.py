"""Tests for the stl (sentinel) encoding/decoding pair."""

from seqpack.encoding.schemes.stl_encoding import encode
from seqpack.decoding.schemes.stl_decoding import decode


class TestStlRoundTrip:
    def test_short_input_returned_unchanged(self):
        # n <= 2 short-circuits and emits an empty snt_pos list
        encoded, aux = encode([5, 7])
        assert encoded == [5, 7]
        assert aux == {"snt_pos": [], "length": 2}
        assert decode(encoded, **aux) == [5, 7]

    def test_no_outliers_returns_original(self):
        values = [10, 11, 12, 13, 14]
        encoded, aux = encode(values)
        assert encoded == values
        assert aux["snt_pos"] == []

    def test_strips_single_outlier(self):
        # Tight cluster around 100 with a stray 0; IQR=5, fence=15, lo=89.
        values = [100, 101, 102, 103, 0, 104, 105, 106, 107, 108]
        encoded, aux = encode(values)
        # The 0 is the sentinel
        assert 0 not in encoded
        assert "snt_ranges" in aux
        assert decode(encoded, **aux) == values

    def test_strips_multiple_sentinel_groups(self):
        values = [100, 100, 0, 0, 100, 100, 100, 0, 100]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_multiple_distinct_sentinel_values(self):
        values = [50, 50, -1, 50, 50, -1, 50, 999, 50, 50]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_strips_float_sentinel(self):
        values = [5.0] * 60 + [999.5] * 30 + [5.0] * 60
        encoded, aux = encode(values)
        assert "snt_ranges" in aux
        assert decode(encoded, **aux) == values

    def test_strips_integer_valued_float_sentinel(self):
        # Sentinel value happens to be integral (999.0) but the sequence
        # is float-typed — the decoded value must stay a float, not int.
        values = [5.0] * 60 + [999.0] * 30 + [5.0] * 60
        encoded, aux = encode(values)
        decoded = decode(encoded, **aux)
        assert decoded == values
        assert all(isinstance(v, float) for v in decoded)

    def test_multiple_distinct_float_sentinel_values(self):
        values = [50.5, 50.5, -1.5, 50.5, 50.5, -1.5, 50.5, 999.5, 50.5, 50.5]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values
