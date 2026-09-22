"""Tests for seqpack.decoding.feature_decode (pandas path)."""

import json

import pytest

from seqpack.decoding.feature_decode import (
    decode_feature,
    decode_feature_payload,
)
from seqpack.encoding.feature_encode import encode_feature_payload
from seqpack.exceptions import DecodingError, InvalidInputError, UnknownSchemeError


class TestDecodeFeature:
    def test_no_scheme_passes_through(self):
        assert decode_feature([1, 2, 3], "", {}) == [1, 2, 3]
        assert decode_feature([1, 2, 3], None, None) == [1, 2, 3]

    def test_pipeline_decoded_in_reverse(self):
        # Encode something, then verify decode_feature handles the reverse order
        from seqpack.encoding.feature_encode import encode_feature

        values = ["a", "b", "a", "a", "c"] * 4
        encoded_value, scheme, aux = encode_feature(values, "cat_bp")
        assert decode_feature(encoded_value, scheme, aux) == values

    def test_none_aux_gives_clear_error_for_aux_consuming_scheme(self):
        # Before the fix, `decode_feature(x, 'cat', None)` raised an opaque
        # "argument of type 'NoneType' is not iterable" because None was
        # indexed directly. Now None normalizes to {}, so a scheme that
        # requires aux (cat needs stoi) fails with a clear missing-argument
        # error instead.
        with pytest.raises(TypeError, match="stoi"):
            decode_feature([0, 1, 0], "cat", None)

    def test_none_aux_is_fine_for_schemes_without_aux(self):
        assert decode_feature([1, 3, 2, 2], "rle", None) == [1, 1, 1, 2, 2]

    def test_unknown_decoding_step_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown decoding step"):
            decode_feature([1, 2, 3], "nosuchscheme", {})

    def test_unknown_decoding_step_raises_unknown_scheme_error(self):
        with pytest.raises(UnknownSchemeError):
            decode_feature([1, 2, 3], "nosuchscheme", {})


class TestDecodeFeaturePayload:
    def test_non_dict_payload_raises_invalid_input_error(self):
        with pytest.raises(InvalidInputError, match="dict"):
            decode_feature_payload([1, 2, 3])
        with pytest.raises(TypeError):
            decode_feature_payload("not a dict")

    def test_malformed_wire_entry_raises_decoding_error(self):
        with pytest.raises(DecodingError):
            decode_feature_payload({"a_enc": json.dumps({"not": "a list"})})
        with pytest.raises(DecodingError):
            decode_feature_payload({"a_enc": json.dumps([])})

    def test_round_trip_through_payload(self):
        payload = {
            "ints": [1, 2, 3, 4, 5] * 5,
            "strings": ["x", "y", "x", "y", "x"] * 5,
        }
        encoded = encode_feature_payload(payload, {"ints": "del_bp", "strings": "cat_bp"})
        decoded = decode_feature_payload(encoded)
        assert decoded == payload

    def test_handles_double_encoded_json(self):
        # Some pipelines (Spark) double-JSON-encode entries; decode_feature_payload
        # transparently handles both single and double JSON wrapping.
        payload = {"a": [1, 2, 3]}
        encoded = encode_feature_payload(payload, {})
        # encoded["a_enc"] is already a JSON string. Wrap it again.
        double = {"a_enc": json.dumps(encoded["a_enc"])}
        decoded = decode_feature_payload(double)
        assert decoded["a"] == [1, 2, 3]

    def test_skips_columns_without_enc_suffix(self):
        # Columns not ending in _enc are ignored
        encoded = {
            "a_enc": json.dumps([[1, 2, 3]]),
            "metadata": "something",
        }
        decoded = decode_feature_payload(encoded)
        assert "a" in decoded
        assert "metadata" not in decoded
