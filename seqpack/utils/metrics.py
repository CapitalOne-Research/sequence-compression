
"""
Utility functions for compression metrics.
"""
from __future__ import annotations

import json
from collections import Counter

import numpy as np
import pandas as pd


def quantization_loss(original: list[float], reconstructed: list[float]) -> dict[str, float]:
    """Measure error between original and reconstructed float arrays.

    Useful for evaluating precision loss from quantization encoding.

    Args:
        original: Original float values before quantization.
        reconstructed: Values after quantize → dequantize round-trip.

    Returns:
        Dictionary with error metrics:
            mae:        Mean Absolute Error
            max_ae:     Maximum Absolute Error
            rmse:       Root Mean Squared Error
            mre:        Mean Relative Error (relative to original; skips zeros)
            snr_db:     Signal-to-Noise Ratio in dB (inf if no error)
            cosine_sim: Cosine similarity in [-1, 1] (1.0 = perfect angular alignment).
    """
    orig = np.asarray(original, dtype=np.float64)
    recon = np.asarray(reconstructed, dtype=np.float64)

    if orig.shape != recon.shape:
        raise ValueError(
            f"Shape mismatch: original {orig.shape} vs reconstructed {recon.shape}"
        )

    if orig.size == 0:
        return {
            "mae": 0.0, "max_ae": 0.0, "rmse": 0.0, "mre": 0.0,
            "snr_db": float("inf"), "cosine_sim": 1.0,
        }

    error = orig - recon
    abs_error = np.abs(error)

    mae = float(np.mean(abs_error))
    max_ae = float(np.max(abs_error))
    rmse = float(np.sqrt(np.mean(error ** 2)))

    # Mean relative error — skip zeros in original to avoid division by zero
    nonzero = orig != 0
    if np.any(nonzero):
        mre = float(np.mean(abs_error[nonzero] / np.abs(orig[nonzero])))
    else:
        mre = 0.0

    # Signal-to-noise ratio
    signal_power = np.mean(orig ** 2)
    noise_power = np.mean(error ** 2)
    if noise_power == 0:
        snr_db = float("inf")
    elif signal_power == 0:
        snr_db = 0.0
    else:
        snr_db = float(10 * np.log10(signal_power / noise_power))

    # Cosine similarity — measures angular alignment, magnitude-independent.
    norm_o = float(np.linalg.norm(orig))
    norm_r = float(np.linalg.norm(recon))
    if norm_o == 0.0 and norm_r == 0.0:
        cosine_sim = 1.0
    elif norm_o == 0.0 or norm_r == 0.0:
        cosine_sim = 0.0
    else:
        cosine_sim = float(np.dot(orig, recon) / (norm_o * norm_r))
        # clamp to [-1, 1] to defend against floating-point overshoot
        cosine_sim = max(-1.0, min(1.0, cosine_sim))

    return {
        "mae": mae,
        "max_ae": max_ae,
        "rmse": rmse,
        "mre": mre,
        "snr_db": snr_db,
        "cosine_sim": cosine_sim,
    }


def verify_payloads_equal(decoded_payload, payload):
    """Verify that decoded payload matches original payload."""
    assert decoded_payload.keys() == payload.keys(), "Keys do not match"
    for key in payload:
        decoded_val = decoded_payload[key]
        original_val = payload[key]
        if isinstance(decoded_val, np.ndarray) or isinstance(original_val, np.ndarray):
            if not np.array_equal(decoded_val, original_val):
                print(f"Mismatch at key '{key}':")
                print(f"  decoded: {decoded_val}")
                print(f"  original: {original_val}")
                return False
        elif decoded_val != original_val:
            print(f"Mismatch at key '{key}':")
            print(f"  decoded: {decoded_val}")
            print(f"  original: {original_val}")
            return False
    return True

def get_sequence_length_from_dict(d):
    for v in d.values():
        if hasattr(v, '__len__') and not isinstance(v, str):
            return len(v)
    return 0

def get_metrics(data: np.ndarray, percentiles: tuple[int, ...] = (25, 50, 75)) -> dict:
    """
    Calculate metrics for a numpy array.

    Args:
        data: Numpy array of values
        percentiles: Tuple of percentiles to calculate (default: (25, 50, 75))

    Returns:
        Dictionary with metrics
    """
    metrics = {
        "mean": np.mean(data),
        "std": np.std(data),
        "min": np.min(data),
        "max": np.max(data),
    }

    for p in percentiles:
        metrics[f"p{p}"] = np.percentile(data, p)

    return metrics


def print_metrics(metrics: dict, format_type: str = None, precision: int = 2):
    """Print metrics in a formatted way.

    Args:
        metrics: Dictionary of metric names to values.
        format_type: Optional formatting - '%' for percentage, 'x' for multiplier, None for raw values.
        precision: Number of decimal places (default 2).
    """
    if not metrics:
        print("No metrics to display.")
        return

    max_key_len = max(len(str(k)) for k in metrics.keys())
    col_width = max_key_len + 4
    val_width = 14

    print("┌" + "─" * col_width + "┬" + "─" * val_width + "┐")
    print(f"│ {'Metric'.ljust(max_key_len + 2)} │ {'Value'.center(val_width - 2)} │")
    print("├" + "─" * col_width + "┼" + "─" * val_width + "┤")

    for key, value in metrics.items():
        if format_type == "%":
            formatted = f"{value * 100:.{precision}f}%"
        elif format_type == "x":
            formatted = f"{value:.{precision}f}x"
        elif isinstance(value, float):
            formatted = f"{value:.{precision}f}"
        else:
            formatted = str(value)

        print(f"│ {str(key).ljust(max_key_len + 2)} │ {formatted.rjust(val_width - 2)} │")

    print("└" + "─" * col_width + "┴" + "─" * val_width + "┘")


def encoding_counter(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count frequency of encoding schemes for each column ending with '_enc'.

    Args:
        df: pandas DataFrame with encoded columns

    Returns:
        DataFrame with columns as index and encoding schemes as columns,
        values are counts. NaN filled with 0.
    """
    per_column = {}

    for col in df.columns:
        if col.endswith('_enc'):
            col_counter = Counter()
            for value in df[col]:
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, (list, tuple)) and len(parsed) > 1:
                            col_counter[parsed[1]] += 1
                        else:
                            col_counter[None] += 1
                    except (json.JSONDecodeError, TypeError):
                        col_counter[None] += 1
                elif isinstance(value, (list, tuple)) and len(value) > 1:
                    col_counter[value[1]] += 1
                else:
                    col_counter[None] += 1
            per_column[col] = dict(col_counter)

    enocding_counts = pd.DataFrame(per_column).T.fillna(0).astype(int)
    if None in enocding_counts.columns:
        enocding_counts = enocding_counts.rename(columns={None: "no_encoding"})
    enocding_counts.loc["total"] = enocding_counts.sum()
    return enocding_counts


def _get_scheme_expr_spark(col_name: str, data_type):
    """Get Spark expression to extract encoding scheme from a column.

    Handles both native array columns and JSON string columns.
    Returns None if the array length is not greater than 1.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.types import ArrayType, StringType

    if isinstance(data_type, StringType):
        arr = F.from_json(F.col(col_name), ArrayType(StringType()))
        return F.when(F.size(arr) > 1, arr.getItem(1)).otherwise(F.lit(None))
    else:
        col = F.col(col_name)
        return F.when(F.size(col) > 1, col.getItem(1)).otherwise(F.lit(None))

def encoding_counter_spark(df) -> pd.DataFrame:
    """
    Count frequency of encoding schemes for each column ending with '_enc'.
    Spark DataFrame version. Handles both array and JSON string columns.

    Args:
        df: Spark DataFrame with encoded columns

    Returns:
        pandas DataFrame with columns as index and encoding schemes as columns,
        values are counts. NaN filled with 0.
    """
    encoded_cols = [(c, df.schema[c].dataType) for c in df.columns if c.endswith('_enc')]
    if not encoded_cols:
        return pd.DataFrame()

    enocding_counts = {}
    for col, data_type in encoded_cols:
        scheme_expr = _get_scheme_expr_spark(col, data_type)
        col_counts = (
            df.select(scheme_expr.alias("scheme"))
            .groupBy("scheme")
            .count()
            .collect()
        )
        enocding_counts[col] = {row["scheme"]: row["count"] for row in col_counts}

    enocding_counts = pd.DataFrame(enocding_counts).T.fillna(0).astype(int)
    enocding_counts.loc["total"] = enocding_counts.sum()
    return enocding_counts.reset_index(names="feature_name")


def print_compression_metrics(df) -> None:
    """Print detailed compression metrics from an encoded DataFrame.

    Expects the DataFrame to contain ``size_before_bytes`` and
    ``size_after_bytes`` columns (produced by ``encode_feature_dataframe``
    with ``metrics=True``).  If a ``sequence_length`` column is present,
    sequence-length statistics are included as well.

    Args:
        df: Encoded DataFrame with metrics columns.
    """
    try:
        import pyspark.sql.functions as F
    except ImportError as e:
        raise ImportError("pyspark is required for print_compression_metrics") from e

    has_seq_len = "sequence_length" in df.columns

    # Derive per-row compression columns.
    df_m = (
        df
        .withColumn("_ratio", F.col("size_before_bytes") / F.col("size_after_bytes"))
        .withColumn(
            "_reduction_pct",
            (1 - F.col("size_after_bytes") / F.col("size_before_bytes")) * 100,
        )
        .withColumn("_bytes_saved", F.col("size_before_bytes") - F.col("size_after_bytes"))
        .withColumn(
            "_is_negative",
            (F.col("size_after_bytes") > F.col("size_before_bytes")).cast("int"),
        )
    )

    # Build all aggregations for a single-pass collect.
    aggs = [
        F.count("*").alias("total_rows"),
        F.sum("size_before_bytes").alias("total_before"),
        F.sum("size_after_bytes").alias("total_after"),
        # Original payload size
        F.mean("size_before_bytes").alias("before_mean"),
        F.stddev("size_before_bytes").alias("before_std"),
        F.min("size_before_bytes").alias("before_min"),
        F.max("size_before_bytes").alias("before_max"),
        F.percentile_approx("size_before_bytes", 0.5).alias("before_p50"),
        F.percentile_approx("size_before_bytes", 0.25).alias("before_p25"),
        F.percentile_approx("size_before_bytes", 0.75).alias("before_p75"),
        F.percentile_approx("size_before_bytes", 0.99).alias("before_p99"),
        # Encoded payload size
        F.mean("size_after_bytes").alias("after_mean"),
        F.stddev("size_after_bytes").alias("after_std"),
        F.min("size_after_bytes").alias("after_min"),
        F.max("size_after_bytes").alias("after_max"),
        F.percentile_approx("size_after_bytes", 0.5).alias("after_p50"),
        F.percentile_approx("size_after_bytes", 0.25).alias("after_p25"),
        F.percentile_approx("size_after_bytes", 0.75).alias("after_p75"),
        F.percentile_approx("size_after_bytes", 0.99).alias("after_p99"),
        # Compression ratio
        F.mean("_ratio").alias("ratio_mean"),
        F.stddev("_ratio").alias("ratio_std"),
        F.min("_ratio").alias("ratio_min"),
        F.max("_ratio").alias("ratio_max"),
        F.percentile_approx("_ratio", 0.5).alias("ratio_p50"),
        F.percentile_approx("_ratio", 0.25).alias("ratio_p25"),
        F.percentile_approx("_ratio", 0.75).alias("ratio_p75"),
        F.percentile_approx("_ratio", 0.99).alias("ratio_p99"),
        # Size reduction %
        F.mean("_reduction_pct").alias("red_mean"),
        F.stddev("_reduction_pct").alias("red_std"),
        F.min("_reduction_pct").alias("red_min"),
        F.max("_reduction_pct").alias("red_max"),
        F.percentile_approx("_reduction_pct", 0.5).alias("red_p50"),
        F.percentile_approx("_reduction_pct", 0.99).alias("red_p99"),
        # Bytes saved
        F.mean("_bytes_saved").alias("saved_mean"),
        F.stddev("_bytes_saved").alias("saved_std"),
        F.min("_bytes_saved").alias("saved_min"),
        F.max("_bytes_saved").alias("saved_max"),
        F.percentile_approx("_bytes_saved", 0.5).alias("saved_p50"),
        F.percentile_approx("_bytes_saved", 0.99).alias("saved_p99"),
        # Negative reduction
        F.sum("_is_negative").alias("negative_count"),
    ]

    if has_seq_len:
        aggs.extend([
            F.mean("sequence_length").alias("seq_mean"),
            F.stddev("sequence_length").alias("seq_std"),
            F.min("sequence_length").alias("seq_min"),
            F.max("sequence_length").alias("seq_max"),
            F.percentile_approx("sequence_length", 0.5).alias("seq_p50"),
            F.percentile_approx("sequence_length", 0.25).alias("seq_p25"),
            F.percentile_approx("sequence_length", 0.75).alias("seq_p75"),
            F.percentile_approx("sequence_length", 0.99).alias("seq_p99"),
        ])

    r = df_m.agg(*aggs).collect()[0].asDict()

    # ---- formatting helpers ------------------------------------------------
    W = 60
    SEP = "-" * W
    DSEP = "=" * W

    def _hdr(title: str) -> str:
        return f"\n{title:^{W}}\n{SEP}"

    def _fi(v) -> str:
        return f"{int(v):,}"

    def _ff(v, d=1) -> str:
        return f"{v:,.{d}f}"

    def _bytes_mb(v) -> str:
        mb = v / (1024 * 1024)
        return f"{_fi(v)} bytes ({_ff(mb, 2)} MB)"

    total_savings = r["total_before"] - r["total_after"]

    # ---- build output ------------------------------------------------------
    lines: list[str] = []

    lines.append(_hdr("DATASET OVERVIEW"))
    lines.append(f"{'Total rows processed:':<31}{_fi(r['total_rows'])}")
    lines.append(f"{'Total original size:':<31}{_bytes_mb(r['total_before'])}")
    lines.append(f"{'Total encoded size:':<31}{_bytes_mb(r['total_after'])}")
    lines.append(f"{'Total savings:':<31}{_bytes_mb(total_savings)}")

    if has_seq_len:
        lines.append(_hdr("SEQUENCE LENGTH STATS"))
        lines.append(f"{'Mean:':<31}{_ff(r['seq_mean'])}")
        lines.append(f"{'Std Dev:':<31}{_ff(r['seq_std'])}")
        lines.append(f"{'Min:':<31}{_fi(r['seq_min'])}")
        lines.append(f"{'Max:':<31}{_fi(r['seq_max'])}")
        lines.append(f"{'Median:':<31}{_ff(r['seq_p50'])}")
        lines.append(f"{'25th percentile:':<31}{_ff(r['seq_p25'])}")
        lines.append(f"{'75th percentile:':<31}{_ff(r['seq_p75'])}")
        lines.append(f"{'99th percentile:':<31}{_ff(r['seq_p99'])}")

    lines.append(_hdr("ORIGINAL PAYLOAD SIZE (bytes)"))
    lines.append(f"{'Mean:':<31}{_fi(r['before_mean'])}")
    lines.append(f"{'Std Dev:':<31}{_fi(r['before_std'])}")
    lines.append(f"{'Min:':<31}{_fi(r['before_min'])}")
    lines.append(f"{'Max:':<31}{_fi(r['before_max'])}")
    lines.append(f"{'Median:':<31}{_fi(r['before_p50'])}")
    lines.append(f"{'25th percentile:':<31}{_fi(r['before_p25'])}")
    lines.append(f"{'75th percentile:':<31}{_fi(r['before_p75'])}")
    lines.append(f"{'99th percentile:':<31}{_fi(r['before_p99'])}")

    lines.append(_hdr("ENCODED PAYLOAD SIZE (bytes)"))
    lines.append(f"{'Mean:':<31}{_fi(r['after_mean'])}")
    lines.append(f"{'Std Dev:':<31}{_fi(r['after_std'])}")
    lines.append(f"{'Min:':<31}{_fi(r['after_min'])}")
    lines.append(f"{'Max:':<31}{_fi(r['after_max'])}")
    lines.append(f"{'Median:':<31}{_fi(r['after_p50'])}")
    lines.append(f"{'25th percentile:':<31}{_fi(r['after_p25'])}")
    lines.append(f"{'75th percentile:':<31}{_fi(r['after_p75'])}")
    lines.append(f"{'99th percentile:':<31}{_fi(r['after_p99'])}")

    lines.append(_hdr("COMPRESSION RATIO (original/encoded)"))
    lines.append(f"{'Mean:':<31}{_ff(r['ratio_mean'], 2)}x")
    lines.append(f"{'Std Dev:':<31}{_ff(r['ratio_std'], 2)}")
    lines.append(f"{'Min:':<31}{_ff(r['ratio_min'], 2)}x")
    lines.append(f"{'Max:':<31}{_ff(r['ratio_max'], 2)}x")
    lines.append(f"{'Median:':<31}{_ff(r['ratio_p50'], 2)}x")
    lines.append(f"{'25th percentile:':<31}{_ff(r['ratio_p25'], 2)}x")
    lines.append(f"{'75th percentile:':<31}{_ff(r['ratio_p75'], 2)}x")
    lines.append(f"{'99th percentile:':<31}{_ff(r['ratio_p99'], 2)}x")

    lines.append(_hdr("SIZE REDUCTION (%)"))
    lines.append(f"{'Mean:':<31}{_ff(r['red_mean'])}%")
    lines.append(f"{'Std Dev:':<31}{_ff(r['red_std'])}%")
    lines.append(f"{'Min:':<31}{_ff(r['red_min'])}%")
    lines.append(f"{'Max:':<31}{_ff(r['red_max'])}%")
    lines.append(f"{'Median:':<31}{_ff(r['red_p50'])}%")
    lines.append(f"{'99th percentile:':<31}{_ff(r['red_p99'])}%")

    lines.append(_hdr("BYTES SAVED PER ROW"))
    lines.append(f"{'Mean:':<31}{_fi(r['saved_mean'])}")
    lines.append(f"{'Std Dev:':<31}{_fi(r['saved_std'])}")
    lines.append(f"{'Min:':<31}{_fi(r['saved_min'])}")
    lines.append(f"{'Max:':<31}{_fi(r['saved_max'])}")
    lines.append(f"{'Median:':<31}{_fi(r['saved_p50'])}")
    lines.append(f"{'99th percentile:':<31}{_fi(r['saved_p99'])}")

    lines.append(f"\n{DSEP}\n")

    negative_pct = (r["negative_count"] / r["total_rows"]) * 100
    lines.append(
        f"Percentage of data with negative size reduction: {_ff(negative_pct, 2)}%"
    )

    print("\n".join(lines))
