"""Spark-optimized wrapper around seqpack's pandas-based encoding utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import pyspark.sql.functions as F

    _PYSPARK_AVAILABLE = True
except ImportError:
    _PYSPARK_AVAILABLE = False

from seqpack.utils.spark_udfs import (
    _byte_size_pandas_udf,
    _make_encode_pandas_udf,
    _make_encoded_size_pandas_udf,
    _normalize_encoding_config,
)

if TYPE_CHECKING:
    from pyspark.sql import DataFrame


def encode_feature_dataframe(
    df: "DataFrame",
    encoding_scheme: dict[str, str | list],
    *,
    drop_originals: bool = True,
    metrics: bool = True,
) -> "DataFrame":
    """Encode feature columns of a Spark DataFrame.

    For each entry in *encoding_scheme* the corresponding DataFrame column
    is encoded using the specified pipeline and the column is renamed to
    the standard ``<name>_enc`` format.

    Args:
        df: Input Spark DataFrame.
        encoding_scheme: Mapping of ``{column_name: encoding_pipeline}``
            where *encoding_pipeline* is either:
            - A string such as ``"cat_bp"`` (underscore-separated encoding steps)
            - A list of candidate pipelines like ``["rle", "bp"]`` to evaluate
              and pick the best compression.
        drop_originals: If ``True`` (default), the original un-encoded
            columns are dropped from the result.
        metrics: If ``True`` (default), three extra columns are added:
            ``size_before_bytes`` and ``size_after_bytes`` containing
            the byte size of the full JSON-serialised payload dict
            (including key names, braces, and separators) before and
            after encoding respectively, and ``sequence_length``
            containing the array length of the first feature column.

    Returns:
        A new DataFrame with the encoded columns.

    Example::

        schema = {"feature_a": "cat_bp", "feature_b": ["rle", "bp"]}
        encoded_df = encode_feature_dataframe(df, schema)
    """
    # Pre-validate and normalize all pipelines so typos surface before a Spark job.
    if not _PYSPARK_AVAILABLE:
        raise ImportError("pyspark is required for encode_feature_dataframe")
    config_by_col: dict[str, dict] = {}
    for col_name, pipeline in encoding_scheme.items():
        config_by_col[col_name] = _normalize_encoding_config(pipeline)

    # Determine which existing columns to retain.
    if drop_originals:
        keep_exprs = [F.col(c) for c in df.columns if c not in encoding_scheme]
    else:
        keep_exprs = [F.col(c) for c in df.columns]

    # Build all new column expressions so they can be computed in one select.
    new_exprs: list = []
    encoded_col_names: list[str] = []
    first_col_name: str | None = None

    for col_name, pipeline in encoding_scheme.items():
        encoded_col_name = f"{col_name}_enc"
        encoded_col_names.append(encoded_col_name)

        encode_udf = _make_encode_pandas_udf(config_by_col[col_name])
        new_exprs.append(
            encode_udf(F.to_json(F.col(col_name))).alias(encoded_col_name)
        )

        if metrics and first_col_name is None:
            first_col_name = col_name

    # Metrics expressions – computed in the same select pass.
    if metrics and encoding_scheme:
        source_cols = list(encoding_scheme.keys())
        new_exprs.append(
            _byte_size_pandas_udf(
                F.to_json(F.struct([F.col(c) for c in source_cols]))
            ).alias("size_before_bytes")
        )
        if first_col_name is not None:
            new_exprs.append(
                F.size(F.col(first_col_name)).alias("sequence_length")
            )

    # Single select replaces the chain of withColumn calls.
    df = df.select(*keep_exprs, *new_exprs)

    # size_after_bytes depends on the encoded columns, so one extra step.
    if metrics and encoded_col_names:
        size_udf = _make_encoded_size_pandas_udf(encoded_col_names)
        df = df.withColumn(
            "size_after_bytes",
            size_udf(*[F.col(c) for c in encoded_col_names]),
        )

    return df
