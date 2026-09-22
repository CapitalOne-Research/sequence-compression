"""Tests for the del (delta) encoding/decoding pair."""

from seqpack.encoding.schemes.delta_encoding import encode
from seqpack.decoding.schemes.delta_decoding import decode


class TestDeltaRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == []
        assert aux == {}
        assert decode(encoded, **aux) == []

    def test_single_element_emits_v0_only(self):
        encoded, aux = encode([42])
        assert encoded == []
        assert aux == {"v0": 42}
        assert decode(encoded, **aux) == [42]

    def test_single_zero_element_is_distinguishable_from_empty(self):
        # Both encode to deltas=[], but only [0] carries v0 in aux -- an
        # absent v0 (decode()'s default) must mean "empty", not "[0]".
        encoded, aux = encode([0])
        assert encoded == []
        assert aux == {"v0": 0}
        assert decode(encoded, **aux) == [0]
        assert decode([]) == []

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

    def test_float_sequence_round_trips_exactly(self):
        values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_negative_floats_round_trip(self):
        values = [-3.25, -1.75, 0.0, 1.25, -0.5]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_mixed_magnitude_floats_round_trip(self):
        values = [0.001, 1234.5, -987.25, 0.0, 42.75]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_large_ints_do_not_overflow(self):
        values = [10**15, 2 * 10**15, 3 * 10**15]
        encoded, aux = encode(values)
        assert decode(encoded, **aux) == values

    def test_del_bp_pipeline_round_trips_integers(self):
        from seqpack.decoding.feature_decode import decode_feature
        from seqpack.encoding.feature_encode import encode_feature

        values = [10 + i for i in range(50)]
        encoded, scheme, aux = encode_feature(values, "del_bp")
        assert scheme == "del_bp"
        assert decode_feature(encoded, scheme, aux) == values
