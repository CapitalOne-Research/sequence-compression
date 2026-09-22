"""seqpack: compress feature sequences into compact JSON-serializable records.

The most common entry points are re-exported here so callers can do::

    from seqpack import encode_feature_df, decode_feature_payload

Spark integration (`seqpack.encoding.spark_feature_encode`,
`seqpack.decoding.spark_feature_decode`) is intentionally not re-exported at
the top level, so `import seqpack` never implies a PySpark dependency.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from seqpack.decoding.feature_decode import decode_feature, decode_feature_payload
from seqpack.encoding.auto_encode import auto_encode
from seqpack.encoding.feature_encode import (
    encode_feature,
    encode_feature_df,
    encode_feature_payload,
    evaluate_candidates,
)
from seqpack.exceptions import (
    DecodingError,
    InvalidInputError,
    SeqPackError,
    UnknownSchemeError,
)
from seqpack.wire import EncodedEntry

try:
    __version__ = version("seqpack")
except PackageNotFoundError:  # pragma: no cover - only hit for an unbuilt checkout
    __version__ = "0.0.0+unknown"

__all__ = [
    "DecodingError",
    "EncodedEntry",
    "InvalidInputError",
    "SeqPackError",
    "UnknownSchemeError",
    "__version__",
    "auto_encode",
    "decode_feature",
    "decode_feature_payload",
    "encode_feature",
    "encode_feature_df",
    "encode_feature_payload",
    "evaluate_candidates",
]
