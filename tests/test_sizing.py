"""Tests for seqpack.utils.sizing."""

import json
from decimal import Decimal

import numpy as np

from seqpack.utils.sizing import (
    _convert_keys_to_native,
    _ensure_list,
    convert_to_json,
    get_json_byte_size,
    get_key_sizes,
    make_json_serializable,
)


class TestEnsureList:
    def test_passes_through_list(self):
        assert _ensure_list([1, 2, 3]) == [1, 2, 3]

    def test_parses_json_string(self):
        assert _ensure_list("[1,2,3]") == [1, 2, 3]

    def test_returns_string_when_not_a_json_list(self):
        # JSON-decodes to a non-list -> returned as-is
        assert _ensure_list("42") == "42"
        assert _ensure_list("not json") == "not json"

    def test_converts_numpy_array(self):
        arr = np.array([1, 2, 3])
        assert _ensure_list(arr) == [1, 2, 3]


class TestConvertToJson:
    def test_compact_separators(self):
        assert convert_to_json([1, 2, 3]) == "[1,2,3]"
        assert convert_to_json({"a": 1, "b": 2}) == '{"a":1,"b":2}'

    def test_serialises_numpy_scalars(self):
        assert convert_to_json(np.int64(5)) == "5"
        assert convert_to_json(np.float64(2.5)) == "2.5"

    def test_serialises_numpy_array(self):
        assert convert_to_json(np.array([1, 2, 3])) == "[1,2,3]"


class TestGetJsonByteSize:
    def test_matches_compact_json_length(self):
        data = [1, 2, 3]
        assert get_json_byte_size(data) == len(json.dumps(data, separators=(",", ":")))

    def test_handles_numpy_keys(self):
        data = {np.int64(1): "a", np.int64(2): "b"}
        # Should not raise; size should equal native-keyed dict
        native = {1: "a", 2: "b"}
        assert get_json_byte_size(data) == get_json_byte_size(native)

    def test_measures_true_utf8_length_for_non_ascii(self):
        # convert_to_json (the wire serialiser) escapes non-ASCII to \uXXXX,
        # which is roughly 2x the real UTF-8 length. Size measurement must
        # use the true UTF-8 length, or non-ASCII columns get penalized.
        data = ["日本語"]
        true_utf8_len = len(
            json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        )
        assert get_json_byte_size(data) == true_utf8_len
        assert get_json_byte_size(data) < len(convert_to_json(data))


class TestConvertKeysToNative:
    def test_recurses_into_nested_structures(self):
        data = {np.int64(1): {"k": [np.int32(2)]}}
        result = _convert_keys_to_native(data)
        # Top-level key converted; values aren't touched (they are JSON-serialised later)
        assert list(result.keys()) == [1]


class TestMakeJsonSerializable:
    def test_decimal_to_int(self):
        assert make_json_serializable(Decimal("3")) == 3

    def test_decimal_to_float(self):
        assert make_json_serializable(Decimal("3.5")) == 3.5

    def test_numpy_array_to_list(self):
        assert make_json_serializable(np.array([1, 2])) == [1, 2]

    def test_recurses(self):
        data = {"a": [Decimal("1.5"), np.array([1, 2])]}
        assert make_json_serializable(data) == {"a": [1.5, [1, 2]]}


class TestGetKeySizes:
    def test_returns_size_per_key(self):
        data = {"a": 1, "abc": 1}
        sizes = get_key_sizes(data)
        # {"a":1} = 7 bytes, {"abc":1} = 9 bytes
        assert sizes["a"] == len('{"a":1}')
        assert sizes["abc"] == len('{"abc":1}')
