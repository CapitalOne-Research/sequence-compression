"""Golden wire-format tests.

The `seqpack.wire.EncodedEntry` refactor centralizes entry construction and
size measurement that used to be hand-rolled at ~10 call sites. These tests
pin the exact serialized wire strings for a small fixed corpus so a future
change to `EncodedEntry` (or anything it touches) cannot silently alter the
compressed output or which encoding scheme wins on size.
"""

from seqpack.encoding.auto_encode import auto_encode
from seqpack.encoding.feature_encode import encode_feature, encode_feature_payload
from seqpack.wire import EncodedEntry

_CORPUS = {
    "ints": [1, 2, 3, 4, 5] * 10,
    "floats": [1.5 + 0.1 * i for i in range(50)],
    "strings": ["a", "b", "a", "a", "c"] * 10,
    "binary": [0, 1, 0, 1, 1, 0] * 20,
    "constant": [7] * 30,
}

_PIPELINES = {
    "strings": "cat_bp",
    "ints": "del_bp",
    "floats": "quant_bp",
    "binary": "bm",
    "constant": "bp",
}


class TestEncodedEntryWireFormat:
    def test_to_wire_drops_falsy_scheme_and_aux(self):
        assert EncodedEntry([1, 2, 3]).to_wire() == [[1, 2, 3]]

    def test_to_wire_keeps_scheme_without_aux(self):
        assert EncodedEntry("AA==", "bm").to_wire() == ["AA==", "bm"]

    def test_to_wire_keeps_scheme_and_aux(self):
        entry = EncodedEntry([1, 2], "del", {"v0": 5})
        assert entry.to_wire() == [[1, 2], "del", {"v0": 5}]

    def test_aux_without_scheme_is_dropped(self):
        # Matches the existing (pre-refactor) behavior: aux is only ever
        # populated alongside a truthy scheme in practice, and the format
        # has no way to represent aux without a scheme name.
        entry = EncodedEntry([1, 2, 3], "", {"stray": 1})
        assert entry.to_wire() == [[1, 2, 3]]

    def test_from_wire_round_trips_all_arities(self):
        for wire in ([1, 2, 3], ["x", "bm"], [[1], "del", {"v0": 1}]):
            entry = EncodedEntry.from_wire(wire)
            assert entry.to_wire() == wire

    def test_byte_size_matches_convert_to_json_length(self):
        from seqpack.utils.sizing import get_json_byte_size

        entry = EncodedEntry([1, 2, 3], "del", {"v0": 5})
        assert entry.byte_size() == get_json_byte_size(entry.to_wire())


class TestGoldenWireOutput:
    """Pin exact serialized output for a fixed corpus (captured pre-refactor)."""

    def test_explicit_pipeline_wire_strings(self):
        expected = {
            "ints": '["AwoAMQe20W2i20W2i20W2i20W2i20W2g","del_bp",{"v0":1}]',
            "floats": (
                '["EAgAMgAABTkKcw+sFOYaHx9ZJJIpzC8FND45eD6xQ+tJJE5eU5dY0V4KY0RofW22cvB4KX1'
                "jgpyH1o0PkkmXgpy7ofWnLqxosaG227wUwU7Gh8vB0PrWM9tt4Kbl4OsZ8FP1jPrG//8="
                '","quant_bp",{"q_scale":7.476920729381247e-05,"q_zp":1.5,"q_bits":16,"q_sym":0}]'
            ),
            "strings": '["AggAMhCEIQhCEIQhCEIQhCA=","cat_bp",{"stoi":{"a":0,"b":1,"c":2}}]',
            "binary": '["eABZZZZZZZZZZZZZZZZZZZY=","bm"]',
            "constant": '["AAwAHg4=","bp"]',
        }
        for name, vals in _CORPUS.items():
            e, s, a = encode_feature(vals, _PIPELINES[name])
            wire = EncodedEntry(e, s, a).to_wire()
            from seqpack.utils.sizing import convert_to_json

            assert convert_to_json(wire) == expected[name], name

    def test_auto_encode_wire_strings_and_scheme_choice(self):
        expected = {
            "ints": ('["AwoAMgIFOApwFOApwFOApwFOApwFOApw","bp"]', "bp"),
            "floats": (
                '["AQoAMfIUVSqlUqpVAA==","quant_del_bp",'
                '{"q_scale":7.476920729381247e-05,"q_zp":1.5,"q_bits":16,"q_sym":0,"v0":0}]',
                "quant_del_bp",
            ),
            "strings": (
                '["AggAMhCEIQhCEIQhCEIQhCA=","cat_bp",{"stoi":{"a":0,"b":1,"c":2}}]',
                "cat_bp",
            ),
            "binary": ('["eABZZZZZZZZZZZZZZZZZZZY=","bm"]', "bm"),
            "constant": ('[[7,30],"rle"]', "rle"),
        }
        from seqpack.utils.sizing import convert_to_json

        for name, vals in _CORPUS.items():
            e, s, a = auto_encode(vals)
            wire = EncodedEntry(e, s, a).to_wire()
            expected_wire, expected_scheme = expected[name]
            assert convert_to_json(wire) == expected_wire, name
            assert s == expected_scheme, name

    def test_payload_wire_strings(self):
        expected = {
            "ints_enc": '["AwoAMgIFOApwFOApwFOApwFOApwFOApw","bp"]',
            "floats_enc": (
                '["AQoAMfIUVSqlUqpVAA==","quant_del_bp",'
                '{"q_scale":7.476920729381247e-05,"q_zp":1.5,"q_bits":16,"q_sym":0,"v0":0}]'
            ),
            "strings_enc": '["AggAMhCEIQhCEIQhCEIQhCA=","cat_bp",{"stoi":{"a":0,"b":1,"c":2}}]',
            "binary_enc": '["eABZZZZZZZZZZZZZZZZZZZY=","bm"]',
            "constant_enc": '[[7,30],"rle"]',
        }
        encoded = encode_feature_payload(dict(_CORPUS))
        assert encoded == expected
