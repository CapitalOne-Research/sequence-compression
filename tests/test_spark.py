"""Tests for the PySpark encode/decode DataFrame API.

Guarded by pytest.importorskip so the suite stays green without the
``spark`` extra installed. The DataFrame round-trip additionally needs a
local JVM (unavailable in some sandboxes) and is skipped gracefully if
Spark fails to boot a session -- the import test below is what actually
catches a regression like the stale `compression.*` imports this file
was added to guard against.
"""

import pytest

pyspark = pytest.importorskip("pyspark")


def test_spark_modules_import_cleanly():
    """Regression test: these three modules used to import a package that
    was renamed away (`compression.*` -> `seqpack.*`), making the entire
    Spark path dead on import."""
    import seqpack.decoding.spark_feature_decode  # noqa: F401
    import seqpack.encoding.spark_feature_encode  # noqa: F401
    import seqpack.utils.spark_udfs  # noqa: F401


@pytest.fixture(scope="module")
def spark_session():
    from pyspark.sql import SparkSession

    try:
        session = (
            SparkSession.builder.master("local[1]")
            .appName("seqpack-tests")
            .config("spark.ui.enabled", "false")
            .getOrCreate()
        )
    except Exception as exc:
        pytest.skip(f"local Spark session unavailable: {exc}")
    yield session
    session.stop()


def test_encode_decode_dataframe_round_trip(spark_session):
    from seqpack.decoding.spark_feature_decode import decode_feature_dataframe
    from seqpack.encoding.spark_feature_encode import encode_feature_dataframe

    df = spark_session.createDataFrame(
        [({"a": [1, 2, 3, 4, 5]},), ({"a": [10, 20, 30, 40, 50]},)],
        ["payload"],
    ).select("payload.a")

    encoded = encode_feature_dataframe(df, {"a": "del_bp"})
    assert "a_enc" in encoded.columns
    assert "a" not in encoded.columns

    decoded = decode_feature_dataframe(encoded)
    rows = [row["a"] for row in decoded.collect()]
    assert sorted(rows) == [[1, 2, 3, 4, 5], [10, 20, 30, 40, 50]]
