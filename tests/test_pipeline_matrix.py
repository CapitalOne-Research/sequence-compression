"""End-to-end round-trip matrix across composed encoding pipelines.

Per-scheme tests (test_bm.py, test_cat.py, etc.) cover individual schemes in
isolation. This file covers multi-step pipelines the README recommends
(e.g. `quant_nbp`, `stl_bp`, `cat_nbp`, `cat_rle_bp`) that were previously
never exercised end-to-end through `encode_feature`/`decode_feature`.
"""

import pytest

from seqpack.decoding.feature_decode import decode_feature
from seqpack.encoding.feature_encode import encode_feature

# (pipeline, values, is_lossy). Lossy pipelines are checked with a
# max-abs-error bound instead of exact equality.
LOSSLESS_PIPELINES = [
    ("cat_bp", ["p", "q", "p", "p", "r"] * 8),
    ("cat_rle", ["x", "x", "y", "y", "y"] * 10),
    ("cat_rle_bp", ["x", "x", "y", "y", "y"] * 10),
    ("cat_nbp", ["a", "a", "a", "b", "a"] * 10),
    ("del_bp", list(range(50))),
    ("del_rle_bp", [1, 1, 1, 2, 2, 2, 3, 3, 3]),
    ("stl_bp", [100] * 30 + [0] * 10 + [100] * 30),
    ("stl_rle_bp", [5] * 20 + [999] * 5 + [5] * 20),
    ("rle_bp", [1, 1, 1, 2, 2, 3, 3, 3, 3]),
]

LOSSY_PIPELINES = [
    ("quant_bp", [i * 0.37 for i in range(40)]),
    ("quant_rle", [1.0] * 20 + [2.0] * 20),
    ("quant_nbp", [1.5] * 20 + [2.75] * 30 + [1.5] * 10),
]


@pytest.mark.parametrize("pipeline,values", LOSSLESS_PIPELINES)
def test_lossless_pipeline_round_trip(pipeline, values):
    encoded, scheme, aux = encode_feature(values, pipeline)
    decoded = decode_feature(encoded, scheme, aux)
    assert decoded == values


@pytest.mark.parametrize("pipeline,values", LOSSY_PIPELINES)
def test_lossy_pipeline_round_trip_within_tolerance(pipeline, values):
    encoded, scheme, aux = encode_feature(values, pipeline)
    decoded = decode_feature(encoded, scheme, aux)
    tolerance = aux.get("q_scale", 0.0) or 1e-9
    assert len(decoded) == len(values)
    assert max(abs(a - b) for a, b in zip(values, decoded)) <= tolerance
