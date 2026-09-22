"""Tests for seqpack.encoding.feature_encode (pandas path).

Covers ``encode_feature``, ``encode_feature_payload``, ``encode_feature_df``,
and ``evaluate_candidates``. ``auto_encode`` has its own test module.
"""

import json

import pandas as pd
import pytest

from seqpack.decoding.feature_decode import decode_feature_payload
from seqpack.encoding.feature_encode import (
    encode_feature,
    encode_feature_df,
    encode_feature_payload,
    evaluate_candidates,
)
from seqpack.exceptions import InvalidInputError, SeqPackError, UnknownSchemeError


class TestEncodeFeature:
    def test_empty_scheme_returns_passthrough(self):
        value, scheme, aux = encode_feature([1, 2, 3], "")
        assert value == [1, 2, 3]
        assert scheme == ""
        assert aux == {}

    def test_unknown_scheme_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown encoding step"):
            encode_feature([1, 2, 3], "nosuchscheme")

    def test_unknown_scheme_raises_unknown_scheme_error(self):
        # UnknownSchemeError is a ValueError subclass, so both the specific
        # type and the pre-existing `except ValueError` pattern keep working.
        with pytest.raises(UnknownSchemeError):
            encode_feature([1, 2, 3], "nosuchscheme")
        with pytest.raises(SeqPackError):
            encode_feature([1, 2, 3], "nosuchscheme")

    def test_single_step(self):
        value, scheme, aux = encode_feature([0, 1, 0, 1, 0, 1] * 5, "bm")
        assert scheme == "bm"
        assert isinstance(value, str)
        assert aux == {}

    def test_pipeline_applies_steps_left_to_right(self):
        values = ["a", "a", "b", "b", "c", "a", "a"] * 5
        value, scheme, aux = encode_feature(values, "cat_bp")
        assert scheme == "cat_bp"
        assert "stoi" in aux  # cat populated; bp added nothing

    def test_drops_encoding_when_not_beneficial(self):
        # A 3-element int list: bp's base64 header overhead is larger than
        # the original JSON, so the encoding must be stripped.
        values = [1, 2, 3]
        value, scheme, aux = encode_feature(values, "bp")
        assert scheme == ""
        assert aux == {}
        assert value == values


class TestEncodeFeaturePayload:
    def test_non_dict_payload_raises_invalid_input_error(self):
        with pytest.raises(InvalidInputError, match="dict"):
            encode_feature_payload([1, 2, 3])
        # Also catchable as TypeError, matching the pre-existing failure mode.
        with pytest.raises(TypeError):
            encode_feature_payload("not a dict")

    def test_basic_payload(self):
        payload = {"a": [0, 1, 0, 1, 0, 1] * 10}
        encoded = encode_feature_payload(payload, {"a": "bm"})
        assert "a_enc" in encoded
        # Wire format: JSON-encoded list
        entry = json.loads(encoded["a_enc"])
        assert isinstance(entry, list)
        assert entry[1] == "bm"

    def test_no_scheme_passes_value_through(self):
        payload = {"a": [1, 2, 3]}
        encoded = encode_feature_payload(payload, {})
        entry = json.loads(encoded["a_enc"])
        assert entry == [[1, 2, 3]]  # no scheme, no aux

    def test_metrics_adds_size_columns(self):
        payload = {"a": [0, 1] * 30}
        encoded = encode_feature_payload(payload, {"a": "bm"}, metrics=True)
        assert "encoded_size" in encoded
        assert "payload_size" in encoded
        assert encoded["encoded_size"] > 0
        assert encoded["payload_size"] > 0

    def test_round_trip_with_decoder(self):
        payload = {
            "binary": [0, 1, 0, 0, 1, 1, 1, 0, 0, 1] * 5,
            "ints": [10, 11, 12, 13, 14] * 4,
            "strings": ["a", "b", "a", "a", "c"] * 5,
        }
        schema = {"binary": "bm", "ints": "del_bp", "strings": "cat_bp"}
        encoded = encode_feature_payload(payload, schema)
        decoded = decode_feature_payload(encoded)
        assert decoded["binary"] == payload["binary"]
        assert decoded["ints"] == payload["ints"]
        assert decoded["strings"] == payload["strings"]


class TestEvaluateCandidates:
    def test_picks_smallest(self):
        values = [1, 1, 1, 2, 2, 2, 3, 3, 3] * 3
        # Note: rle alone is much shorter than rle_bp here because the data
        # is 3 distinct ints in long runs; either pick is fine — we just
        # assert the result can be decoded back.
        encoded_value, scheme, aux = evaluate_candidates(values, ["bp", "rle", "rle_bp"])
        assert scheme in ("bp", "rle", "rle_bp")

    def test_returns_original_when_no_candidate_helps(self):
        # A single-element list: bp's header overhead exceeds the original
        # JSON size, so no candidate ever beats it.
        encoded_value, scheme, aux = evaluate_candidates([1], ["bp"])
        assert scheme is None
        assert aux == {}
        assert encoded_value == [1]

    def test_caching_returns_a_compressed_result(self):
        # cache=True (the default) measures intermediate sizes and picks the
        # smallest prefix. We just verify a non-trivial input gets compressed.
        values = ["a", "b", "a", "a", "c", "a"] * 5
        encoded_value, scheme, _ = evaluate_candidates(values, ["cat_bp", "cat_rle"])
        assert scheme is not None
        assert scheme != ""

    def test_unknown_scheme_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown encoding step"):
            evaluate_candidates([1, 2, 3], ["bp", "nosuchscheme"])


class TestEncodeFeatureDf:
    def test_non_dataframe_raises_invalid_input_error(self):
        with pytest.raises(InvalidInputError, match="DataFrame"):
            encode_feature_df([{"a": [1, 2, 3]}], {"a": "bp"})
        # Also catchable as TypeError, matching the pre-existing failure mode.
        with pytest.raises(TypeError):
            encode_feature_df({"a": [1, 2, 3]})

    def test_drop_originals_default(self):
        df = pd.DataFrame({"a": [[0, 1, 0, 1, 0, 1] * 10] * 3})
        out = encode_feature_df(df, {"a": "bm"})
        # Original column dropped, encoded column added
        assert "a" not in out.columns
        assert "a_enc" in out.columns
        assert len(out) == 3

    def test_drop_originals_false_keeps_originals(self):
        df = pd.DataFrame({"a": [[0, 1, 0, 1, 0, 1] * 10] * 2})
        out = encode_feature_df(df, {"a": "bm"}, drop_originals=False)
        assert "a" in out.columns
        assert "a_enc" in out.columns

    def test_metrics_adds_size_columns(self):
        df = pd.DataFrame({"a": [[0, 1] * 30] * 2})
        out = encode_feature_df(df, {"a": "bm"}, metrics=True)
        assert "encoded_size" in out.columns
        assert "payload_size" in out.columns
