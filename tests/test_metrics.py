"""Tests for seqpack.utils.metrics (non-Spark functions only)."""

import math

import numpy as np
import pandas as pd
import pytest

from seqpack.utils.metrics import (
    encoding_counter,
    get_metrics,
    get_sequence_length_from_dict,
    print_metrics,
    quantization_loss,
    verify_payloads_equal,
)


class TestQuantizationLoss:
    def test_zero_error(self):
        loss = quantization_loss([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert loss["mae"] == 0.0
        assert loss["rmse"] == 0.0
        assert loss["snr_db"] == float("inf")

    def test_uniform_error(self):
        loss = quantization_loss([10.0, 20.0, 30.0], [10.5, 20.5, 30.5])
        assert math.isclose(loss["mae"], 0.5)
        assert math.isclose(loss["max_ae"], 0.5)
        assert math.isclose(loss["rmse"], 0.5)

    def test_empty(self):
        loss = quantization_loss([], [])
        assert loss["mae"] == 0.0
        assert loss["max_ae"] == 0.0
        assert loss["rmse"] == 0.0
        assert loss["mre"] == 0.0
        assert loss["snr_db"] == float("inf")

    def test_skips_zero_originals_in_mre(self):
        # Original has a 0; mre should ignore it (no division by zero)
        loss = quantization_loss([0.0, 10.0], [0.5, 10.5])
        assert loss["mre"] == 0.05  # |10-10.5|/10

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            quantization_loss([1.0, 2.0], [1.0])


class TestVerifyPayloadsEqual:
    def test_equal_dicts(self):
        a = {"x": [1, 2, 3], "y": ["a", "b"]}
        assert verify_payloads_equal(a, dict(a)) is True

    def test_different_values(self):
        assert verify_payloads_equal({"x": [1, 2]}, {"x": [1, 3]}) is False

    def test_numpy_arrays_equal(self):
        a = {"x": np.array([1, 2, 3])}
        b = {"x": np.array([1, 2, 3])}
        assert verify_payloads_equal(a, b) is True

    def test_numpy_arrays_unequal(self):
        a = {"x": np.array([1, 2, 3])}
        b = {"x": np.array([1, 2, 4])}
        assert verify_payloads_equal(a, b) is False


class TestGetSequenceLengthFromDict:
    def test_finds_first_sized_value(self):
        d = {"a": [1, 2, 3], "b": [1, 2]}
        assert get_sequence_length_from_dict(d) == 3

    def test_skips_strings(self):
        d = {"name": "abcd", "values": [1, 2]}
        assert get_sequence_length_from_dict(d) == 2

    def test_no_sized_values(self):
        d = {"name": "abcd", "x": 5}
        assert get_sequence_length_from_dict(d) == 0


class TestGetMetrics:
    def test_basic_stats(self):
        m = get_metrics(np.array([1, 2, 3, 4, 5]))
        assert m["min"] == 1
        assert m["max"] == 5
        assert math.isclose(m["mean"], 3.0)
        assert "p25" in m and "p50" in m and "p75" in m

    def test_custom_percentiles(self):
        m = get_metrics(np.array([1, 2, 3, 4, 5]), percentiles=(10, 90))
        assert "p10" in m and "p90" in m


class TestPrintMetrics:
    def test_does_not_crash(self, capsys):
        print_metrics({"a": 1.5, "b": 2.0})
        captured = capsys.readouterr()
        assert "a" in captured.out
        assert "b" in captured.out

    def test_empty_dict(self, capsys):
        print_metrics({})
        captured = capsys.readouterr()
        assert "No metrics" in captured.out

    def test_percent_format(self, capsys):
        print_metrics({"reduction": 0.5}, format_type="%")
        captured = capsys.readouterr()
        assert "%" in captured.out


class TestEncodingCounter:
    def test_counts_schemes_per_column(self):
        df = pd.DataFrame({
            "a_enc": [["v", "bp"], ["v", "bp"], ["v", "rle"]],
            "b_enc": [["v"], ["v", "cat_bp"], ["v"]],
            "non_enc_col": [1, 2, 3],
        })
        counts = encoding_counter(df)
        # Index has the encoded columns plus a "total" row
        assert "a_enc" in counts.index
        assert "b_enc" in counts.index
        assert "total" in counts.index
        # Non-encoded columns excluded
        assert "non_enc_col" not in counts.index
        # Counts add up
        assert counts.loc["a_enc", "bp"] == 2
        assert counts.loc["a_enc", "rle"] == 1
