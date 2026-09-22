"""Tests for tbqm and tbqp encoding (scheme contract + round-trip)."""

import numpy as np
import pytest

from seqpack.encoding.schemes.tbqm_encoding import encode as tbqm_encode
from seqpack.encoding.schemes.tbqp_encoding import encode as tbqp_encode
from seqpack.encoding.feature_encode import encode_feature


# ─── tbqm ─────────────────────────────────────────────────────────────────

def test_tbqm_returns_int_list_and_dict():
    x = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8]
    result, aux = tbqm_encode(x)
    assert isinstance(result, list)
    assert all(isinstance(v, int) for v in result)
    assert len(result) == len(x)
    assert isinstance(aux, dict)


def test_tbqm_aux_keys():
    x = [0.1, 0.2, 0.3, 0.4, 0.5]
    _, aux = tbqm_encode(x)
    assert set(aux.keys()) == {"tq_dim", "tq_bits", "tq_seed", "tq_norm"}
    assert aux["tq_dim"] == 5
    assert aux["tq_bits"] == 4
    assert aux["tq_seed"] == 42
    assert abs(aux["tq_norm"] - np.linalg.norm(x)) < 1e-10


def test_tbqm_deterministic_by_seed():
    x = list(np.random.default_rng(7).standard_normal(16))
    r1, _ = tbqm_encode(x, seed=10)
    r2, _ = tbqm_encode(x, seed=10)
    r3, _ = tbqm_encode(x, seed=99)
    assert r1 == r2
    assert r1 != r3


def test_tbqm_num_bits_respected():
    x = list(np.random.default_rng(0).standard_normal(8))
    r4, aux4 = tbqm_encode(x, num_bits=4)
    r2, aux2 = tbqm_encode(x, num_bits=2)
    assert aux4["tq_bits"] == 4
    assert aux2["tq_bits"] == 2
    assert max(r4) < 2 ** 4
    assert max(r2) < 2 ** 2


def test_tbqm_rejects_short_vector():
    with pytest.raises(ValueError, match="length >= 3"):
        tbqm_encode([0.1, 0.2])


def test_tbqm_rejects_invalid_bits():
    x = [0.1] * 8
    with pytest.raises(ValueError):
        tbqm_encode(x, num_bits=0)
    with pytest.raises(ValueError):
        tbqm_encode(x, num_bits=9)


# ─── tbqp ─────────────────────────────────────────────────────────────────

def test_tbqp_returns_int_list_and_dict():
    x = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8]
    result, aux = tbqp_encode(x)
    assert isinstance(result, list)
    assert all(isinstance(v, int) for v in result)
    assert len(result) == len(x)
    assert isinstance(aux, dict)


def test_tbqp_aux_keys():
    x = [0.1, 0.2, 0.3, 0.4, 0.5]
    _, aux = tbqp_encode(x)
    assert set(aux.keys()) == {"tq_dim", "tq_bits", "tq_seed", "tq_norm", "tq_rnorm", "tq_qseed", "tq_signs"}
    assert aux["tq_dim"] == 5
    assert aux["tq_bits"] == 4
    assert aux["tq_qseed"] == 43
    # tq_signs is now a bm-encoded base64 string
    assert isinstance(aux["tq_signs"], str)


def test_tbqp_rejects_short_vector():
    with pytest.raises(ValueError, match="length >= 3"):
        tbqp_encode([0.1, 0.2])


def test_tbqp_rejects_one_bit():
    x = [0.1] * 8
    with pytest.raises(ValueError):
        tbqp_encode(x, num_bits=1)


def test_tbqp_deterministic():
    x = list(np.random.default_rng(5).standard_normal(12))
    r1, _ = tbqp_encode(x, seed=10, qjl_seed=20)
    r2, _ = tbqp_encode(x, seed=10, qjl_seed=20)
    assert r1 == r2


# ─── pipeline contract ────────────────────────────────────────────────────

def test_tbqm_via_pipeline_returns_int_list_and_correct_scheme():
    x = list(np.random.default_rng(1).standard_normal(16))
    val, scheme, aux = encode_feature(x, "tbqm")
    assert scheme == "tbqm"
    assert isinstance(val, list)
    assert all(isinstance(v, int) for v in val)


def test_tbqp_via_pipeline_returns_int_list_and_correct_scheme():
    x = list(np.random.default_rng(2).standard_normal(16))
    val, scheme, aux = encode_feature(x, "tbqp")
    assert scheme == "tbqp"
    assert isinstance(val, list)
    assert all(isinstance(v, int) for v in val)


def test_tbqm_composable_with_bp():
    x = list(np.random.default_rng(3).standard_normal(16))
    val, scheme, aux = encode_feature(x, "tbqm_bp")
    assert scheme == "tbqm_bp"


def test_tbqp_composable_with_bp():
    x = list(np.random.default_rng(4).standard_normal(16))
    val, scheme, aux = encode_feature(x, "tbqp_bp")
    assert scheme == "tbqp_bp"
