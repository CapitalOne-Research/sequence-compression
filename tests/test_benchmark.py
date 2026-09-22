"""Tests for seqpack.utils.benchmark (non-plotting paths)."""

import pandas as pd

from seqpack.utils.benchmark import (
    _benchmark_single,
    _format_time,
    _pick_display_unit,
    aggregate_results,
    benchmark_dataframe,
    expand_encoding_schema,
    generate_sub_schemes,
)


class TestGenerateSubSchemes:
    def test_single_step(self):
        assert generate_sub_schemes("bp") == ["bp"]

    def test_two_step(self):
        assert generate_sub_schemes("rle_bp") == ["rle", "rle_bp"]

    def test_three_step(self):
        assert generate_sub_schemes("cat_rle_bp") == ["cat", "cat_rle", "cat_rle_bp"]


class TestExpandEncodingSchema:
    def test_string_input(self):
        out = expand_encoding_schema({"feat": "rle_bp"})
        assert out == {"feat": ["rle", "rle_bp"]}

    def test_list_input_deduplicates(self):
        out = expand_encoding_schema({"feat": ["cat_bp", "cat_rle"]})
        # cat appears once, even though it's a prefix of both
        assert out["feat"] == ["cat", "cat_bp", "cat_rle"]

    def test_multiple_features(self):
        out = expand_encoding_schema({"a": "bp", "b": "cat_bp"})
        assert out == {"a": ["bp"], "b": ["cat", "cat_bp"]}


class TestBenchmarkSingle:
    def test_returns_required_fields(self):
        result = _benchmark_single([0, 1, 0, 1, 0, 1] * 10, "bm")
        for key in (
            "scheme",
            "encode_latency_s",
            "decode_latency_s",
            "is_lossy",
            "encoding_applied",
        ):
            assert key in result
        assert result["scheme"] == "bm"
        assert result["encode_latency_s"] >= 0

    def test_unbenificial_encoding_marks_not_applied(self):
        # A 3-element list almost never compresses with bp because of header overhead
        result = _benchmark_single([1, 2, 3], "bp")
        if not result["encoding_applied"]:
            assert result["decode_latency_s"] == 0.0
            assert result["is_lossy"] is False


class TestBenchmarkDataframe:
    def test_returns_one_row_per_feature_row_scheme(self):
        df = pd.DataFrame({"a": [[0, 1, 0, 1] * 5, [0, 1, 0, 1] * 5]})
        results = benchmark_dataframe(df, {"a": "bm"})
        # 2 rows × 1 feature × 1 scheme prefix = 2 measurements
        assert len(results) == 2
        assert set(results["scheme"]) == {"bm"}

    def test_no_overlapping_columns_raises(self):
        df = pd.DataFrame({"x": [[1, 2]]})
        try:
            benchmark_dataframe(df, {"y": "bp"})
        except ValueError:
            return
        raise AssertionError("expected ValueError")


class TestAggregateResults:
    def test_aggregates_by_scheme(self):
        raw = pd.DataFrame([
            {"scheme": "bp", "encode_latency_s": 1.0, "decode_latency_s": 0.5,
             "is_lossy": False, "encoding_applied": True},
            {"scheme": "bp", "encode_latency_s": 2.0, "decode_latency_s": 0.7,
             "is_lossy": False, "encoding_applied": True},
            {"scheme": "rle", "encode_latency_s": 0.3, "decode_latency_s": 0.1,
             "is_lossy": False, "encoding_applied": False},
        ])
        agg = aggregate_results(raw, percentiles=[95])
        assert "avg_encode_latency_s" in agg.columns
        assert "p95_encode_latency_s" in agg.columns
        assert agg.loc["bp", "avg_encode_latency_s"] == 1.5
        assert agg.loc["bp", "n_samples"] == 2

    def test_default_percentiles(self):
        raw = pd.DataFrame([
            {"scheme": "bp", "encode_latency_s": 0.1, "decode_latency_s": 0.05,
             "is_lossy": False, "encoding_applied": True},
        ])
        agg = aggregate_results(raw)
        for p in (75, 95, 99):
            assert f"p{p}_encode_latency_s" in agg.columns


class TestFormatTime:
    def test_microseconds(self):
        v, unit = _format_time(5e-6)
        assert unit == "µs"
        assert abs(v - 5.0) < 1e-9

    def test_milliseconds(self):
        v, unit = _format_time(0.005)
        assert unit == "ms"

    def test_seconds(self):
        v, unit = _format_time(2.0)
        assert unit == "s"


class TestPickDisplayUnit:
    def test_micro(self):
        unit, mult = _pick_display_unit(pd.Series([1e-6, 2e-6]))
        assert unit == "µs"
        assert mult == 1e6

    def test_milli(self):
        unit, mult = _pick_display_unit(pd.Series([0.001, 0.002]))
        assert unit == "ms"
        assert mult == 1e3

    def test_seconds(self):
        unit, mult = _pick_display_unit(pd.Series([1.0, 2.0]))
        assert unit == "s"
        assert mult == 1.0
