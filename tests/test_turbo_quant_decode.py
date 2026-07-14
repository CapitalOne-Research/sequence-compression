"""Tests for tbqm and tbqp decoding (round-trip reconstruction quality)."""

import numpy as np
import pytest

from c1.aiml.compression.encoding.feature_encode import encode_feature
from c1.aiml.compression.decoding.feature_decode import decode_feature
from c1.aiml.compression.decoding.schemes.tbqm_decoding import decode as tbqm_decode
from c1.aiml.compression.decoding.schemes.tbqp_decoding import decode as tbqp_decode
from c1.aiml.compression.encoding.schemes.tbqm_encoding import encode as tbqm_encode
from c1.aiml.compression.encoding.schemes.tbqp_encoding import encode as tbqp_encode


def _rmse(a, b):
    return float(np.sqrt(np.mean((np.array(a) - np.array(b)) ** 2)))


# ─── tbqm decode ──────────────────────────────────────────────────────────

def test_tbqm_decode_empty():
    assert tbqm_decode([]) == []
    assert tbqm_decode([], tq_dim=0) == []


def test_tbqm_round_trip_length():
    x = list(np.random.default_rng(10).standard_normal(32))
    indices, aux = tbqm_encode(x)
    result = tbqm_decode(indices, **aux)
    assert len(result) == len(x)


def test_tbqm_round_trip_rmse_reasonable():
    x = list(np.random.default_rng(11).standard_normal(64))
    indices, aux = tbqm_encode(x, num_bits=4)
    result = tbqm_decode(indices, **aux)
    err = _rmse(x, result)
    assert err < 1.0, f"RMSE {err:.4f} unexpectedly high"


def test_tbqm_higher_bits_lower_error():
    x = list(np.random.default_rng(12).standard_normal(64))
    idx_2, aux_2 = tbqm_encode(x, num_bits=2)
    idx_6, aux_6 = tbqm_encode(x, num_bits=6)
    err_2 = _rmse(x, tbqm_decode(idx_2, **aux_2))
    err_6 = _rmse(x, tbqm_decode(idx_6, **aux_6))
    assert err_6 < err_2


def test_tbqm_pipeline_round_trip():
    x = list(np.random.default_rng(13).standard_normal(20))
    val, scheme, aux = encode_feature(x, "tbqm")
    assert scheme == "tbqm"
    decoded = decode_feature(val, scheme, aux)
    assert len(decoded) == len(x)
    assert _rmse(x, decoded) < 1.0


def test_tbqm_norm_preserved():
    x = list(np.random.default_rng(14).standard_normal(16))
    indices, aux = tbqm_encode(x)
    result = tbqm_decode(indices, **aux)
    assert abs(np.linalg.norm(result) - np.linalg.norm(x)) / np.linalg.norm(x) < 0.1


def test_tbqm_bp_pipeline_round_trip():
    x = list(np.random.default_rng(15).standard_normal(20))
    val, scheme, aux = encode_feature(x, "tbqm_bp")
    assert scheme == "tbqm_bp"
    decoded = decode_feature(val, scheme, aux)
    assert len(decoded) == len(x)
    assert _rmse(x, decoded) < 1.0


# ─── tbqp decode ──────────────────────────────────────────────────────────

def test_tbqp_decode_empty():
    assert tbqp_decode([]) == []
    assert tbqp_decode([], tq_dim=0) == []


def test_tbqp_round_trip_length():
    x = list(np.random.default_rng(20).standard_normal(32))
    indices, aux = tbqp_encode(x)
    result = tbqp_decode(indices, **aux)
    assert len(result) == len(x)


def test_tbqp_round_trip_rmse_reasonable():
    x = list(np.random.default_rng(21).standard_normal(64))
    indices, aux = tbqp_encode(x, num_bits=4)
    result = tbqp_decode(indices, **aux)
    err = _rmse(x, result)
    assert err < 1.5, f"RMSE {err:.4f} unexpectedly high"


def test_tbqp_pipeline_round_trip():
    x = list(np.random.default_rng(22).standard_normal(20))
    val, scheme, aux = encode_feature(x, "tbqp")
    assert scheme == "tbqp"
    decoded = decode_feature(val, scheme, aux)
    assert len(decoded) == len(x)


def test_tbqp_bp_pipeline_round_trip():
    x = list(np.random.default_rng(23).standard_normal(20))
    val, scheme, aux = encode_feature(x, "tbqp_bp")
    assert scheme == "tbqp_bp"
    decoded = decode_feature(val, scheme, aux)
    assert len(decoded) == len(x)


# ─── edge cases ───────────────────────────────────────────────────────────

def test_short_vector_not_encoded_via_pipeline():
    x = [0.5, -0.5]
    with pytest.raises((ValueError, Exception)):
        tbqm_encode(x)
