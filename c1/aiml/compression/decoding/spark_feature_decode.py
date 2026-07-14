"""Spark-optimized wrappers around feature_transform decoding utilities.

Provides a high-level entry point:
- ``decode_feature_dataframe`` – a function that decodes specified encoded
  feature columns of a DataFrame (returning a new DataFrame with decoded
  columns).
"""

try:
    from pyspark.sql import DataFrame
    import pyspark.sql.functions as F
    _PYSPARK_AVAILABLE = True
except ImportError:
    _PYSPARK_AVAILABLE = False

from c1.aiml.compression.utils.spark_udfs import _make_decode_pandas_udf, _cast_json_columns


def decode_feature_dataframe(
    df,
    encoded_columns: list[str] | None = None,
    *,
    drop_originals: bool = True,
    suffix: str = "_enc",
):
    """Decode encoded feature columns of a Spark DataFrame.

    For each encoded column the corresponding value is decoded using the
    encoding scheme embedded in the encoded payload and the column is
    renamed to the original feature name (stripping the ``_enc`` suffix).

    Args:
        df: Input Spark DataFrame containing encoded columns.
        encoded_columns: List of encoded column names to decode. If ``None``
            (default), all columns ending with *suffix* are decoded.
        drop_originals: If ``True`` (default), the original encoded
            columns are dropped from the result.
        suffix: The suffix used to identify encoded columns (default
            ``"_enc"``). The decoded column name is derived by stripping
            this suffix.

    Returns:
        A new DataFrame with the decoded columns.

    Example::

        decoded_df = decode_feature_dataframe(encoded_df)
        # or explicitly:
        decoded_df = decode_feature_dataframe(
            encoded_df, ["feature_a_enc", "feature_b_enc"]
        )
    """
    if not _PYSPARK_AVAILABLE:
        raise ImportError("pyspark is required for decode_feature_dataframe")
    # Auto-detect encoded columns if not provided.
    if encoded_columns is None:
        encoded_columns = [c for c in df.columns if c.endswith(suffix)]

    if not encoded_columns:
        return df

    # Determine which existing columns to retain.
    if drop_originals:
        keep_exprs = [F.col(c) for c in df.columns if c not in encoded_columns]
    else:
        keep_exprs = [F.col(c) for c in df.columns]

    # Build all new decoded column expressions.
    decode_udf = _make_decode_pandas_udf()
    new_exprs: list = []
    decoded_col_names: list[str] = []

    for col_name in encoded_columns:
        # Derive the decoded column name by stripping the suffix.
        if col_name.endswith(suffix):
            decoded_col_name = col_name[: -len(suffix)]
        else:
            decoded_col_name = f"{col_name}_decoded"

        decoded_col_names.append(decoded_col_name)
        new_exprs.append(
            decode_udf(F.col(col_name)).alias(decoded_col_name)
        )

    df = df.select(*keep_exprs, *new_exprs)

    df = _cast_json_columns(df, decoded_col_names)

    return df
