"""Latency benchmarking for compression encoding schemes.

Measures encode/decode latency and lossiness per encoding scheme across a
DataFrame, then visualizes results with plotly.
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from c1.aiml.compression.encoding.feature_encode import (
    ENCODING_SCHEMES,
    encode_feature,
)
from c1.aiml.compression.utils.sizing import _ensure_list
from c1.aiml.compression.decoding.feature_decode import decode_feature


# ---------------------------------------------------------------------------
# Sub-scheme generation
# ---------------------------------------------------------------------------

def generate_sub_schemes(pipeline: str) -> list[str]:
    """Generate all contiguous-prefix sub-schemes from a pipeline string.

    Given ``"rle_bp"``, returns ``["rle", "rle_bp"]``.
    Given ``"cat_rle_bp"``, returns ``["cat", "cat_rle", "cat_rle_bp"]``.
    A single-step pipeline like ``"bp"`` returns ``["bp"]``.
    """
    steps = pipeline.split("_")
    return ["_".join(steps[: i + 1]) for i in range(len(steps))]


def expand_encoding_schema(encoding_schema: dict[str, str | list[str]]) -> dict[str, list[str]]:
    """Expand each feature's pipeline into all prefix sub-scheme variants.

    Args:
        encoding_schema: Mapping of feature name to a pipeline string
            (e.g. ``{"feat": "rle_bp"}``) or a list of candidate pipelines
            (e.g. ``{"feat": ["cat_bp", "cat_rle"]}``).

    Returns:
        Mapping of feature name to deduplicated list of sub-scheme strings
        to benchmark (e.g. ``{"feat": ["cat", "cat_bp", "cat_rle"]}``).
    """
    expanded = {}
    for feature, pipeline in encoding_schema.items():
        pipelines = pipeline if isinstance(pipeline, list) else [pipeline]
        seen = set()
        variants = []
        for p in pipelines:
            for sub in generate_sub_schemes(p):
                if sub not in seen:
                    seen.add(sub)
                    variants.append(sub)
        expanded[feature] = variants
    return expanded


# ---------------------------------------------------------------------------
# Single-sequence measurement
# ---------------------------------------------------------------------------

def _benchmark_single(
    values: list,
    scheme: str,
) -> dict:
    """Benchmark encode + decode for one sequence and one scheme.

    Returns a dict with keys:
        scheme, encode_latency_s, decode_latency_s, is_lossy
    """

    # --- encode ---
    t0 = time.perf_counter()
    encoded_value, encoding_scheme, auxiliary_info = encode_feature(values, scheme)
    encode_time = time.perf_counter() - t0

    # If encoding was rejected (not beneficial), still record the attempt.
    # encode_feature returns ({}, None) for scheme/aux when encoding isn't beneficial.
    if not encoding_scheme:
        return {
            "scheme": scheme,
            "encode_latency_s": encode_time,
            "decode_latency_s": 0.0,
            "is_lossy": False,
            "encoding_applied": False,
        }

    # --- decode ---

    t0 = time.perf_counter()
    decoded_value = decode_feature(encoded_value, scheme, auxiliary_info)
    decode_time = time.perf_counter() - t0

    # --- lossiness check ---
    is_lossy = decoded_value != values

    return {
        "scheme": scheme,
        "encode_latency_s": encode_time,
        "decode_latency_s": decode_time,
        "is_lossy": is_lossy,
        "encoding_applied": True,
    }


# ---------------------------------------------------------------------------
# Full benchmark
# ---------------------------------------------------------------------------

def benchmark_dataframe(
    df: pd.DataFrame,
    encoding_schema: dict[str, str | list[str]],
) -> pd.DataFrame:
    """Run latency benchmarks for every feature × row × sub-scheme.

    Args:
        df: Raw (unencoded) DataFrame. Only columns present in
            ``encoding_schema`` are benchmarked.
        encoding_schema: Mapping of feature name to pipeline string.

    Returns:
        DataFrame with one row per (feature, row_index, scheme) measurement.
        Columns: feature, row_idx, scheme, encode_latency_s, decode_latency_s,
        is_lossy, encoding_applied.
    """
    expanded = expand_encoding_schema(encoding_schema)

    # Filter to features present in both schema and dataframe
    features = [f for f in expanded if f in df.columns]
    if not features:
        raise ValueError(
            "No overlapping columns between encoding_schema and DataFrame."
        )

    records: list[dict] = []
    total_rows = len(df)
    for row_idx in range(total_rows):
        if (row_idx + 1) % 100 == 0 or (row_idx + 1) == total_rows:
            print(f"Benchmarking rows: {row_idx + 1}/{total_rows}")
        for feature in features:
            raw = _ensure_list(df[feature].iloc[row_idx])
            for scheme in expanded[feature]:
                result = _benchmark_single(raw, scheme)
                result["feature"] = feature
                result["row_idx"] = row_idx
                records.append(result)

    return pd.DataFrame(records)


def aggregate_results(
    raw_results: pd.DataFrame,
    percentiles: list[int] | None = None,
) -> pd.DataFrame:
    """Aggregate per-measurement results into per-scheme summary.

    Args:
        raw_results: Raw benchmark results from :func:`benchmark_dataframe`.
        percentiles: List of percentiles to compute (e.g. [75, 95, 99]).
            Defaults to [75, 95, 99] if not provided.

    Returns a DataFrame indexed by ``scheme`` with columns:
        avg_encode_latency_s, avg_decode_latency_s, p{N}_encode_latency_s,
        p{N}_decode_latency_s for each percentile N, is_lossy, n_samples,
        pct_encoding_applied.
    """
    if percentiles is None:
        percentiles = [75, 95, 99]

    grouped = raw_results.groupby("scheme")

    agg_dict = {
        "avg_encode_latency_s": grouped["encode_latency_s"].mean(),
        "avg_decode_latency_s": grouped["decode_latency_s"].mean(),
    }

    for p in percentiles:
        agg_dict[f"p{p}_encode_latency_s"] = grouped["encode_latency_s"].quantile(p / 100)
        agg_dict[f"p{p}_decode_latency_s"] = grouped["decode_latency_s"].quantile(p / 100)

    agg_dict.update({
        "is_lossy": grouped["is_lossy"].any(),
        "n_samples": grouped["scheme"].count(),
        "pct_encoding_applied": grouped["encoding_applied"].mean() * 100,
    })

    agg = pd.DataFrame(agg_dict)
    agg = agg.sort_values("avg_encode_latency_s", ascending=True)
    return agg


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def _require_plotly():
    """Lazily import plotly; raise a clear error if not installed."""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ModuleNotFoundError:
        raise ModuleNotFoundError(
            "plotly is required for latency visualization. "
            "Install it with: pip install '.[benchmark]'"
        ) from None
    return go, make_subplots

def _format_time(seconds: float) -> tuple[float, str]:
    """Pick the best time unit and return (converted_value, unit_label)."""
    if seconds < 1e-3:
        return seconds * 1e6, "µs"
    if seconds < 1.0:
        return seconds * 1e3, "ms"
    return seconds, "s"


def _pick_display_unit(values: pd.Series) -> tuple[str, float]:
    """Choose a single display unit for a series of latencies in seconds."""
    median = values.median()
    if median < 1e-3:
        return "µs", 1e6
    if median < 1.0:
        return "ms", 1e3
    return "s", 1.0


def plot_results(
    agg: pd.DataFrame,
    output_dir: str | Path | None = None,
    show: bool = True,
    percentiles: list[int] | None = None,
):
    """Create a plotly bar chart of encoding scheme latency with percentiles.

    Args:
        agg: Aggregated results from :func:`aggregate_results`.
        output_dir: If provided, save ``latency_benchmark.html`` and
            ``latency_benchmark.png`` to this directory.
        show: Whether to call ``fig.show()`` for interactive display.
        percentiles: List of percentiles to plot (e.g. [75, 95, 99]).
            Defaults to [75, 95, 99]. Must match percentiles used in
            :func:`aggregate_results`.

    Returns:
        The plotly Figure.
    """
    if percentiles is None:
        percentiles = [75, 95, 99]

    go, make_subplots = _require_plotly()

    schemes = agg.index.tolist()

    # Collect all latency columns for unit selection
    latency_cols = ["avg_encode_latency_s", "avg_decode_latency_s"]
    for p in percentiles:
        latency_cols.extend([f"p{p}_encode_latency_s", f"p{p}_decode_latency_s"])
    all_latencies = pd.concat([agg[col] for col in latency_cols if col in agg.columns])
    unit_label, multiplier = _pick_display_unit(all_latencies)

    # Lossy annotations
    lossy_markers = ["*" if v else "" for v in agg["is_lossy"]]
    display_names = [f"{s}{m}" for s, m in zip(schemes, lossy_markers)]

    fig = make_subplots(rows=1, cols=2, subplot_titles=("Encode Latency", "Decode Latency"))

    # Define metrics to plot: (label, column_suffix)
    metrics = [("Mean", "avg")] + [(f"P{p}", f"p{p}") for p in percentiles]

    # Color palette for metrics
    colors = ["#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A", "#19D3F3"]

    for i, (label, col_prefix) in enumerate(metrics):
        color = colors[i % len(colors)]

        # Encode trace
        encode_col = f"{col_prefix}_encode_latency_s"
        if encode_col in agg.columns:
            fig.add_trace(go.Bar(
                x=display_names,
                y=agg[encode_col] * multiplier,
                name=label,
                marker_color=color,
                legendgroup=label,
                showlegend=True,
                hovertemplate=f"<b>%{{x}}</b><br>{label} Encode: %{{y:.2f}} {unit_label}<extra></extra>",
            ), row=1, col=1)

        # Decode trace
        decode_col = f"{col_prefix}_decode_latency_s"
        if decode_col in agg.columns:
            fig.add_trace(go.Bar(
                x=display_names,
                y=agg[decode_col] * multiplier,
                name=label,
                marker_color=color,
                legendgroup=label,
                showlegend=False,
                hovertemplate=f"<b>%{{x}}</b><br>{label} Decode: %{{y:.2f}} {unit_label}<extra></extra>",
            ), row=1, col=2)

    fig.update_layout(
        title="Encoding Scheme Latency Benchmark",
        barmode="group",
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1),
        height=500,
        width=1400,
    )
    fig.update_xaxes(title_text="Encoding Scheme (* = lossy)", row=1, col=1)
    fig.update_xaxes(title_text="Encoding Scheme (* = lossy)", row=1, col=2)
    fig.update_yaxes(title_text=f"Latency ({unit_label})", row=1, col=1)
    fig.update_yaxes(title_text=f"Latency ({unit_label})", row=1, col=2)

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        fig.write_html(str(output_dir / "latency_benchmark.html"))
        try:
            fig.write_image(str(output_dir / "latency_benchmark.png"), width=1400, height=600)
        except Exception:
            print("Warning: could not export PNG (kaleido/Chrome may not be available). HTML saved.")

    if show:
        fig.show()

    return fig


def print_summary_table(agg: pd.DataFrame) -> None:
    """Print a formatted summary table to stdout."""
    unit_label, multiplier = _pick_display_unit(
        pd.concat([agg["avg_encode_latency_s"], agg["avg_decode_latency_s"]])
    )

    header = (
        f"{'Scheme':<16} "
        f"{'Encode (' + unit_label + ')':>14} "
        f"{'Decode (' + unit_label + ')':>14} "
        f"{'Lossy':>7} "
        f"{'Applied %':>10} "
        f"{'Samples':>8}"
    )
    sep = "─" * len(header)
    print(sep)
    print(header)
    print(sep)
    for scheme, row in agg.iterrows():
        print(
            f"{scheme:<16} "
            f"{row['avg_encode_latency_s'] * multiplier:>14.2f} "
            f"{row['avg_decode_latency_s'] * multiplier:>14.2f} "
            f"{'yes' if row['is_lossy'] else 'no':>7} "
            f"{row['pct_encoding_applied']:>9.1f}% "
            f"{int(row['n_samples']):>8}"
        )
    print(sep)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_benchmark(
    df: pd.DataFrame,
    encoding_schema: dict[str, str | list[str]] | str | Path,
    output_dir: str | Path | None = None,
    show: bool = True,
    percentiles: list[int] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, object]:
    """Run a full latency benchmark and produce visualizations.

    Args:
        df: Raw DataFrame with feature columns.
        encoding_schema: Either a dict mapping feature names to pipeline
            strings, or a path to a JSON file containing such a dict.
        output_dir: Directory to save HTML/PNG plots. ``None`` to skip saving.
        show: Whether to display the interactive plotly chart.
        percentiles: List of percentiles to compute and plot (e.g. [75, 95, 99]).
            Defaults to [75, 95, 99] if not provided.

    Returns:
        Tuple of (raw_results, aggregated_results, plotly_figure).
    """
    # Load schema from file if needed
    if isinstance(encoding_schema, (str, Path)):
        with open(encoding_schema) as f:
            encoding_schema = json.load(f)

    raw_results = benchmark_dataframe(df, encoding_schema)
    agg = aggregate_results(raw_results, percentiles=percentiles)
    print_summary_table(agg)
    fig = plot_results(agg, output_dir=output_dir, show=show, percentiles=percentiles)
    return raw_results, agg, fig
