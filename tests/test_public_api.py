"""Tests for the top-level `seqpack` package surface.

Covers `__version__` and the re-exports declared in `seqpack/__init__.py`
(and `__all__`) — the entry points documented in the README as
``from seqpack import ...``.
"""

import pandas as pd
import pytest

import seqpack


class TestVersion:
    def test_version_is_a_non_empty_string(self):
        assert isinstance(seqpack.__version__, str)
        assert seqpack.__version__

    def test_version_matches_installed_distribution_metadata(self):
        from importlib.metadata import version

        assert seqpack.__version__ == version("seqpack")


class TestAllMatchesExports:
    def test_every_name_in_all_is_importable(self):
        for name in seqpack.__all__:
            assert hasattr(seqpack, name), f"seqpack.__all__ lists {name!r} but it isn't exported"

    def test_all_has_no_duplicates(self):
        assert len(seqpack.__all__) == len(set(seqpack.__all__))


class TestTopLevelEncodeDecodeRoundTrip:
    def test_payload_round_trip_using_only_top_level_imports(self):
        payload = {"ints": [10, 11, 12, 13, 14] * 4, "strings": ["a", "b", "a", "a", "c"] * 5}
        schema = {"ints": "del_bp", "strings": "cat_bp"}

        encoded = seqpack.encode_feature_payload(payload, schema)
        decoded = seqpack.decode_feature_payload(encoded)

        assert decoded == payload

    def test_dataframe_round_trip_using_only_top_level_imports(self):
        df = pd.DataFrame({"a": [[0, 1, 0, 1, 0, 1] * 10] * 3})
        encoded_df = seqpack.encode_feature_df(df, {"a": "bm"})
        assert "a_enc" in encoded_df.columns

    def test_auto_encode_is_exported(self):
        value, scheme, aux = seqpack.auto_encode([0, 1, 0, 1, 0, 1] * 10)
        assert isinstance(scheme, str)

    def test_encoded_entry_round_trips_through_wire(self):
        entry = seqpack.EncodedEntry([1, 2, 3], "bp", {})
        wire = entry.to_wire()
        assert seqpack.EncodedEntry.from_wire(wire).value == [1, 2, 3]


class TestExceptionHierarchy:
    def test_seqpack_error_is_the_common_base(self):
        assert issubclass(seqpack.UnknownSchemeError, seqpack.SeqPackError)
        assert issubclass(seqpack.InvalidInputError, seqpack.SeqPackError)
        assert issubclass(seqpack.DecodingError, seqpack.SeqPackError)

    def test_exceptions_remain_catchable_as_builtins(self):
        assert issubclass(seqpack.UnknownSchemeError, ValueError)
        assert issubclass(seqpack.InvalidInputError, TypeError)
        assert issubclass(seqpack.DecodingError, ValueError)

    def test_bad_payload_type_raises_seqpack_error(self):
        with pytest.raises(seqpack.SeqPackError):
            seqpack.encode_feature_payload([1, 2, 3])

    def test_unknown_scheme_raises_seqpack_error(self):
        with pytest.raises(seqpack.SeqPackError):
            seqpack.encode_feature([1, 2, 3], "nosuchscheme")


class TestSparkNotImportedAtTopLevel:
    def test_importing_seqpack_does_not_require_pyspark(self):
        # `import seqpack` must not transitively import pyspark: users who
        # never touch the Spark path shouldn't need the `spark` extra
        # installed. We can't uninstall pyspark here, so instead assert the
        # Spark modules are absent from sys.modules immediately after a
        # fresh import of the top-level package.
        import importlib
        import sys

        for mod in list(sys.modules):
            if mod == "seqpack" or mod.startswith("seqpack."):
                del sys.modules[mod]

        importlib.import_module("seqpack")

        assert "seqpack.encoding.spark_feature_encode" not in sys.modules
        assert "seqpack.decoding.spark_feature_decode" not in sys.modules
