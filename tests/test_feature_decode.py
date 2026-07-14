"""Tests for c1.aiml.compression.decoding.feature_decode (pandas path)."""

import json

from c1.aiml.compression.decoding.feature_decode import (
    decode_feature,
    decode_feature_payload,
)
from c1.aiml.compression.encoding.feature_encode import encode_feature_payload


class TestDecodeFeature:
    def test_no_scheme_passes_through(self):
        assert decode_feature([1, 2, 3], "", {}) == [1, 2, 3]
        assert decode_feature([1, 2, 3], None, None) == [1, 2, 3]

    def test_pipeline_decoded_in_reverse(self):
        # Encode something, then verify decode_feature handles the reverse order
        from c1.aiml.compression.encoding.feature_encode import encode_feature

        values = ["a", "b", "a", "a", "c"] * 4
        encoded_value, scheme, aux = encode_feature(values, "cat_bp")
        assert decode_feature(encoded_value, scheme, aux) == values


class TestDecodeFeaturePayload:
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
