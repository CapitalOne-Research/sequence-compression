import json
from typing import Optional

try:
    import pyspark.sql.functions as F
    from pyspark.sql import DataFrame
    from pyspark.sql.types import IntegerType, MapType, StringType
    _PYSPARK_AVAILABLE = True
except ImportError:
    _PYSPARK_AVAILABLE = False

import pandas as pd

from compression.encoding.feature_encode import (
    encode_feature,
    encode_feature_payload,
    evaluate_candidates,
    ENCODING_SCHEMES,
)
from compression.decoding.feature_decode import decode_feature

# ---------------------------------------------------------------------------
# UDF: operates on a single MapType column containing the full payload dict
# ---------------------------------------------------------------------------

def _encode_payload_map(payload_map: dict, encoding_schema_json: Optional[str]) -> dict:
    """Pure-Python callable for use inside a PySpark UDF.

    All values in the returned map are JSON-serialised strings so the result
    fits inside a ``MapType(StringType(), StringType())``.
    """
    if payload_map is None:
        return None

    encoding_schema = json.loads(encoding_schema_json) if encoding_schema_json else None
    encoded = encode_feature_payload(payload_map, encoding_schema=encoding_schema)

    # Serialise every value to a JSON string so the map is homogeneous.
    # encode_feature_payload returns [value], [value, scheme], or [value, scheme, aux_info].
    return {k: json.dumps(v) for k, v in encoded.items()}


def _get_encode_feature_payload_udf(encoding_schema: Optional[dict] = None):
    """Return a PySpark UDF that encodes a MapType payload column.

    Args:
        encoding_schema: Optional encoding schema dict passed through to
            ``encode_feature_payload``.  If ``None`` the encoding steps
            are inferred from feature names.

    Returns:
        A PySpark Column expression that can be used in
        ``df.withColumn(...)``.

    Example::

        udf_expr = get_encode_feature_payload_udf({"feature_a": "cat_bp"})
        encoded_df = df.withColumn("encoded_payload", udf_expr(F.col("payload")))
    """
    schema_json = json.dumps(encoding_schema) if encoding_schema else None

    @F.udf(MapType(StringType(), StringType()))
    def _udf(payload_map):
        return _encode_payload_map(payload_map, schema_json)

    return _udf


# ---------------------------------------------------------------------------
# DataFrame-level API: encode individual feature columns
# ---------------------------------------------------------------------------

def _encode_column_value(value_json: str, encoding_config_json: str) -> str:
    """Encode a single feature value given encoding configuration.

    Both input and output are JSON strings so the UDF signature stays
    ``StringType -> StringType``.
    
    Args:
        value_json: JSON-serialized feature value.
        encoding_config_json: JSON object with 'type' ('steps' or 'candidates')
            and 'value' (comma-separated steps or list of candidate pipelines).
    """
    if value_json is None:
        return None

    feature_value = json.loads(value_json)
    config = json.loads(encoding_config_json)
    
    if config['type'] == 'candidates':
        # List of candidate pipelines - evaluate and pick best
        encoded_value, encoding_scheme, auxiliary_info = evaluate_candidates(
            feature_value, config['value']
        )
    else:
        # Single pipeline as underscore-separated string
        encoded_value, encoding_scheme, auxiliary_info = encode_feature(feature_value, config['value'])
    
    entry = [encoded_value]
    if encoding_scheme:
        entry.append(encoding_scheme)
    if auxiliary_info:
        entry.append(auxiliary_info)
    return json.dumps(entry)


_encode_column_udf = F.udf(_encode_column_value, StringType()) if _PYSPARK_AVAILABLE else None


def _byte_size(value_json: str) -> int:
    """Return the byte length of a JSON-serialised value."""
    if value_json is None:
        return None
    return len(value_json.encode("utf-8"))


_byte_size_udf = F.udf(_byte_size, IntegerType()) if _PYSPARK_AVAILABLE else None


def _make_encode_pandas_udf(encoding_config: dict):
    """Return a vectorised (Arrow-backed) UDF for a specific encoding configuration.
    
    Args:
        encoding_config: Dict with 'type' ('steps' or 'candidates') and 'value'.
    """
    config_type = encoding_config['type']
    config_value = encoding_config['value']

    @F.pandas_udf(StringType())
    def _udf(value_json_series: pd.Series) -> pd.Series:
        def _encode_one(v):
            if v is None:
                return None
            feature_value = json.loads(v)
            if config_type == 'candidates':
                encoded_value, encoding_scheme, auxiliary_info = evaluate_candidates(
                    feature_value, config_value
                )
            else:
                encoded_value, encoding_scheme, auxiliary_info = encode_feature(feature_value, config_value)
            entry = [encoded_value]
            if encoding_scheme:
                entry.append(encoding_scheme)
            if auxiliary_info:
                entry.append(auxiliary_info)
            return json.dumps(entry)
        return value_json_series.apply(_encode_one)

    return _udf


def _byte_size_pandas_impl(value_json_series: pd.Series) -> pd.Series:
    """Vectorised byte-size UDF."""
    return value_json_series.apply(
        lambda v: None if v is None else len(v.encode("utf-8"))
    )


_byte_size_pandas_udf = F.pandas_udf(_byte_size_pandas_impl, IntegerType()) if _PYSPARK_AVAILABLE else None


def _make_encoded_size_pandas_udf(encoded_col_names: list[str]):
    """Return a pandas UDF that computes compact JSON size for encoded columns.
    
    Each encoded column contains a JSON string. This UDF deserializes them,
    builds a proper dict, and measures the compact JSON serialization.
    """
    col_names = list(encoded_col_names)  # capture for closure
    
    @F.pandas_udf(IntegerType())
    def _udf(*cols: pd.Series) -> pd.Series:
        def _compute_size(row_values):
            payload = {}
            for col_name, val in zip(col_names, row_values):
                if val is not None:
                    payload[col_name] = json.loads(val)
            return len(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        
        # Combine all columns into rows
        combined = pd.concat(cols, axis=1)
        return combined.apply(lambda row: _compute_size(row.values), axis=1)
    
    return _udf


def _make_decode_pandas_udf():
    """Return a vectorised (Arrow-backed) UDF that decodes an encoded column.

    Each encoded column value is a JSON string in the format:
        [encoded_value, encoding_scheme, auxiliary_info]
    The UDF decodes it back to the original feature value and returns
    the result as a JSON string.
    """

    @F.pandas_udf(StringType())
    def _udf(encoded_json_series: pd.Series) -> pd.Series:
        def _decode_one(v):
            if v is None:
                return None
            entry = json.loads(v)
            # Handle double-encoded JSON strings
            if isinstance(entry, str):
                entry = json.loads(entry)

            encoded_value = entry[0]
            encoding_scheme = entry[1] if len(entry) > 1 else ""
            auxiliary_info = entry[2] if len(entry) > 2 else {}

            decoded = decode_feature(encoded_value, encoding_scheme, auxiliary_info)
            return json.dumps(decoded)

        return encoded_json_series.apply(_decode_one)

    return _udf


def _normalize_encoding_config(pipeline) -> dict:
    """Normalize encoding pipeline to a config dict.
    
    Args:
        pipeline: Either a string like "cat_bp" or a list like ["rle", "bp"].
        
    Returns:
        Dict with 'type' ('steps' or 'candidates') and 'value'.
    """
    if isinstance(pipeline, list):
        # List of candidate pipelines to evaluate
        return {'type': 'candidates', 'value': pipeline}
    else:
        # Single pipeline as underscore-separated string
        steps = pipeline.split("_")
        # Validate steps exist
        for step in steps:
            if step not in ENCODING_SCHEMES:
                raise ValueError(f"Unknown encoding step: {step}")
        return {'type': 'steps', 'value': pipeline}

def _cast_json_columns(df: DataFrame, col_names: list[str]) -> DataFrame:
    """Parse JSON-string columns into native Spark types via schema inference.

    Samples one non-null value per column, uses ``schema_of_json`` to derive
    the Spark DDL type string, and applies ``from_json`` to convert.
    """
    if not col_names:
        return df

    # One Spark action to grab a single non-null sample per column.
    sample_row = df.select(
        *[F.first(F.col(c), ignorenulls=True).alias(c) for c in col_names]
    ).first()

    if sample_row is None:
        return df

    # Infer the DDL schema for every sample in one local pass, then apply.
    for col_name in col_names:
        sample_val = sample_row[col_name]
        if sample_val is None:
            continue
        schema_col = F.schema_of_json(F.lit(sample_val))
        df = df.withColumn(col_name, F.from_json(F.col(col_name), schema_col))

    return df
