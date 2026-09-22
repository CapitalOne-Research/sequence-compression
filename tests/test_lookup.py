"""Tests for seqpack.utils.lookup."""

from typing import get_type_hints

from seqpack.utils.lookup import (
    DECODE_PARAMS,
    DECODING_SCHEMES,
    ENCODE_PARAMS,
    ENCODING_SCHEMES,
)
from seqpack.wire import AUX_SCHEMAS

EXPECTED_SHORT_CODES = {"bm", "bp", "cat", "del", "nbp", "quant", "rle", "stl", "tbqm", "tbqp"}


def test_all_codes_present_in_both_directions():
    assert set(ENCODING_SCHEMES) == EXPECTED_SHORT_CODES
    assert set(DECODING_SCHEMES) == EXPECTED_SHORT_CODES


def test_every_encoder_exposes_an_encode_callable():
    for name, module in ENCODING_SCHEMES.items():
        assert callable(getattr(module, "encode", None)), f"{name} missing encode()"


def test_every_decoder_exposes_a_decode_callable():
    for name, module in DECODING_SCHEMES.items():
        assert callable(getattr(module, "decode", None)), f"{name} missing decode()"


def test_encode_params_match_known_signatures():
    # Spot-check the keyword args we rely on elsewhere
    assert ENCODE_PARAMS["bp"] == ["bits_per_value"]
    assert ENCODE_PARAMS["cat"] == ["frequency_sorted"]
    assert ENCODE_PARAMS["quant"] == ["num_bits"]
    assert ENCODE_PARAMS["stl"] == ["iqr_factor"]
    # Stateless / no-tunable encoders
    for name in ("bm", "del", "nbp", "rle"):
        assert ENCODE_PARAMS[name] == []
    # TurboQuant
    assert set(ENCODE_PARAMS["tbqm"]) == {"num_bits", "seed"}
    assert set(ENCODE_PARAMS["tbqp"]) == {"num_bits", "seed", "qjl_seed"}


def test_decode_params_match_known_signatures():
    assert DECODE_PARAMS["cat"] == ["stoi"]
    assert DECODE_PARAMS["del"] == ["v0"]
    assert set(DECODE_PARAMS["quant"]) == {"q_scale", "q_zp", "q_bits", "q_sym"}
    assert set(DECODE_PARAMS["stl"]) == {"snt_pos", "snt_ranges", "length"}
    for name in ("bm", "bp", "nbp", "rle"):
        assert DECODE_PARAMS[name] == []
    # TurboQuant
    assert set(DECODE_PARAMS["tbqm"]) == {"tq_dim", "tq_bits", "tq_seed", "tq_norm"}
    assert set(DECODE_PARAMS["tbqp"]) == {"tq_dim", "tq_bits", "tq_seed", "tq_norm", "tq_rnorm", "tq_qseed", "tq_signs"}


def test_aux_schemas_match_decode_params():
    # decode_feature dispatches aux kwargs to decode() by parameter name
    # (feature_decode.py). If a scheme's AUX_SCHEMAS TypedDict and its
    # decode() signature drift apart, a typo silently drops a decode
    # parameter instead of raising -- this pins the two together.
    assert set(AUX_SCHEMAS) == set(DECODE_PARAMS)
    for code, schema in AUX_SCHEMAS.items():
        assert set(get_type_hints(schema)) == set(DECODE_PARAMS[code]), code
