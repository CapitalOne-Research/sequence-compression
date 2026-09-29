"""Packers (bp, nbp, bm) must reject non-integer input instead of truncating it.

Regression coverage for silent float corruption: `int(v)` coercion turned
e.g. `del_bp` on [0.7, 0.7005, ...] into an all-zero delta stream that
decoded to [0.7, 0.7, ...] with no error.
"""

import pytest

from seqpack import decode_feature_payload, encode_feature_payload
from seqpack.encoding.schemes import bm_encoding, bp_encoding, nbp_encoding
from seqpack.exceptions import InvalidInputError

PACKERS = {"bp": bp_encoding, "nbp": nbp_encoding, "bm": bm_encoding}


@pytest.mark.parametrize("name", PACKERS)
def test_fractional_floats_rejected(name):
    with pytest.raises(InvalidInputError, match=name):
        PACKERS[name].encode([0.0, 1.0, 0.5, 1.0])


@pytest.mark.parametrize("name", PACKERS)
def test_integer_valued_floats_still_accepted(name):
    encoded, _ = PACKERS[name].encode([0.0, 1.0, 1.0, 0.0])
    assert isinstance(encoded, str)


@pytest.mark.parametrize("pipeline", ["bp", "del_bp", "del_nbp", "rle_bp"])
def test_float_pipelines_raise_instead_of_corrupting(pipeline):
    values = [round(0.7 + 0.0005 * i, 4) for i in range(60)]
    with pytest.raises(InvalidInputError):
        encode_feature_payload({"x": values}, {"x": pipeline})


def test_quant_pipelines_unaffected():
    values = [round(0.7 + 0.0005 * i, 4) for i in range(60)]
    decoded = decode_feature_payload(encode_feature_payload({"x": values}, {"x": "quant_del_bp"}))["x"]
    assert max(abs(a - b) for a, b in zip(values, decoded, strict=True)) < 1e-4
