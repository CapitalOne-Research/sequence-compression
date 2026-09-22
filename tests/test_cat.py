"""Tests for the cat (categorical) encoding/decoding pair."""

from seqpack.encoding.schemes.cat_encoding import encode
from seqpack.decoding.schemes.cat_decoding import decode


class TestCatRoundTrip:
    def test_empty(self):
        encoded, aux = encode([])
        assert encoded == []
        assert aux == {"stoi": {}}
        assert decode(encoded, aux["stoi"]) == []

    def test_round_trip_basic(self):
        values = ["a", "b", "a", "c", "b", "a"]
        encoded, aux = encode(values)
        assert decode(encoded, aux["stoi"]) == values

    def test_frequency_sorted_assigns_zero_to_most_common(self):
        values = ["x", "y", "x", "x", "z"]
        encoded, aux = encode(values, frequency_sorted=True)
        # 'x' is most frequent -> id 0
        assert aux["stoi"]["x"] == 0

    def test_first_appearance_order(self):
        values = ["b", "a", "b", "c"]
        encoded, aux = encode(values, frequency_sorted=False)
        assert aux["stoi"] == {"b": 0, "a": 1, "c": 2}
        assert encoded == [0, 1, 0, 2]
        assert decode(encoded, aux["stoi"]) == values

    def test_single_unique_value(self):
        values = ["only"] * 8
        encoded, aux = encode(values)
        assert aux["stoi"] == {"only": 0}
        assert encoded == [0] * 8
        assert decode(encoded, aux["stoi"]) == values

    def test_alphabetical_tiebreak_in_freq_sort(self):
        values = ["b", "a"]  # both frequency 1, alphabetical tiebreak
        _, aux = encode(values, frequency_sorted=True)
        assert aux["stoi"]["a"] < aux["stoi"]["b"]
